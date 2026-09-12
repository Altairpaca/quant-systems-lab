#pragma once
#include <condition_variable>
#include <cstddef>
#include <deque>
#include <mutex>
#include <optional>
#include <stdexcept>
#include <type_traits>

namespace qsl {
// Correctness baseline, not lock-free. Callers must join all users before destruction.
template<class T> class BoundedQueue {
    static_assert(std::is_nothrow_move_constructible_v<T>);
    std::mutex mutex_;
    std::condition_variable readable_, writable_;
    std::deque<T> rows_;
    std::size_t capacity_;
    bool closed_ = false;
public:
    explicit BoundedQueue(std::size_t capacity) : capacity_(capacity) {
        if (!capacity) throw std::invalid_argument("capacity must be positive");
    }
    bool push(T value) {
        std::unique_lock lock(mutex_);
        writable_.wait(lock, [&] { return closed_ || rows_.size() < capacity_; });
        if (closed_) return false;
        rows_.push_back(std::move(value));
        readable_.notify_one(); return true;
    }
    std::optional<T> pop() {
        std::unique_lock lock(mutex_);
        readable_.wait(lock, [&] { return closed_ || !rows_.empty(); });
        if (rows_.empty()) return std::nullopt;
        T value = std::move(rows_.front()); rows_.pop_front();
        writable_.notify_one(); return value;
    }
    void close() { // reject new writes, drain accepted events
        std::lock_guard lock(mutex_); closed_ = true;
        readable_.notify_all(); writable_.notify_all();
    }
    std::size_t cancel() { // explicit abort: discard pending events, return discard count
        std::lock_guard lock(mutex_); closed_ = true;
        auto dropped = rows_.size(); rows_.clear();
        readable_.notify_all(); writable_.notify_all(); return dropped;
    }
};
} // namespace qsl
