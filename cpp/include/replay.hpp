#pragma once
#include <algorithm>
#include <cstdint>
#include <functional>
#include <limits>
#include <queue>
#include <stdexcept>
#include <tuple>
#include <vector>
#include <utility>

namespace qsl {
struct Event {
    std::uint64_t available_ns, feed, seq;
    std::int64_t venue_ns, price_ticks, qty;
    auto key() const { return std::tie(available_ns, feed, seq); }
    bool operator==(const Event&) const = default;
};
using Feeds = std::vector<std::vector<Event>>;

// Own validated immutable inputs. Timestamp ties across feeds are a policy,
// not evidence of a true exchange-wide ordering.
class Replay {
    Feeds feeds_;
    std::size_t count_ = 0;
public:
    explicit Replay(Feeds feeds) : feeds_(std::move(feeds)) {
        for (std::size_t f = 0; f < feeds_.size(); ++f) {
            const auto& rows = feeds_[f];
            if (rows.size() > std::numeric_limits<std::size_t>::max() - count_)
                throw std::length_error("event count overflow");
            count_ += rows.size();
            for (std::size_t i = 0; i < rows.size(); ++i) {
                if (rows[i].feed != f) throw std::invalid_argument("feed mismatch");
                if (i && (rows[i].available_ns < rows[i-1].available_ns ||
                          rows[i].seq <= rows[i-1].seq))
                    throw std::invalid_argument("non-monotone feed or sequence");
            }
        }
    }
    std::size_t size() const { return count_; }
    std::vector<Event> reference() const {
        std::vector<Event> out; out.reserve(count_);
        for (const auto& f : feeds_) out.insert(out.end(), f.begin(), f.end());
        std::stable_sort(out.begin(), out.end(), [](const auto& a, const auto& b) { return a.key() < b.key(); });
        return out;
    }
    std::vector<Event> scan() const {
        std::vector<Event> out; out.reserve(count_);
        std::vector<std::size_t> pos(feeds_.size());
        for (std::size_t n = 0; n < count_; ++n) {
            std::size_t best = feeds_.size();
            for (std::size_t f = 0; f < feeds_.size(); ++f) {
                if (pos[f] == feeds_[f].size()) continue;
                if (best == feeds_.size() || feeds_[f][pos[f]].key() < feeds_[best][pos[best]].key()) best = f;
            }
            out.push_back(feeds_[best][pos[best]++]);
        }
        return out;
    }
    std::vector<Event> heap_replace() const {
        using Cursor = std::tuple<std::uint64_t, std::uint64_t, std::uint64_t, std::size_t>;
        std::vector<Cursor> heads; heads.reserve(feeds_.size());
        for (std::size_t f = 0; f < feeds_.size(); ++f)
            if (!feeds_[f].empty()) heads.emplace_back(feeds_[f][0].available_ns, f, feeds_[f][0].seq, 0);
        std::make_heap(heads.begin(), heads.end(), std::greater<Cursor>{});
        std::vector<Event> out; out.reserve(count_);
        while (!heads.empty()) {
            const auto [ts, feed, seq, pos] = heads.front();
            (void)ts; (void)seq;
            const auto& rows = feeds_[feed]; out.push_back(rows[pos]);
            if (pos + 1 < rows.size()) {
                const auto& e = rows[pos+1];
                heads.front() = Cursor{e.available_ns, feed, e.seq, pos+1};
            } else {
                heads.front() = heads.back(); heads.pop_back();
            }
            // A validated feed's next key cannot precede its previous key.
            // Replace the root with one downward sift, instead of pop then push.
            if (heads.empty()) break;
            std::size_t parent = 0;
            auto replacement = heads.front();
            while (parent < heads.size()/2) {
                std::size_t child = parent*2+1;
                if (child+1 < heads.size() && heads[child+1] < heads[child]) ++child;
                if (!(heads[child] < replacement)) break;
                heads[parent] = heads[child]; parent = child;
            }
            heads[parent] = replacement;
        }
        return out;
    }
    std::vector<Event> heap() const {
        // copied immutable key + input position; no per-event owning allocation.
        using Cursor = std::tuple<std::uint64_t, std::uint64_t, std::uint64_t, std::size_t>;
        std::vector<Cursor> storage; storage.reserve(feeds_.size());
        for (std::size_t f = 0; f < feeds_.size(); ++f)
            if (!feeds_[f].empty()) storage.emplace_back(feeds_[f][0].available_ns, f, feeds_[f][0].seq, 0);
        std::priority_queue<Cursor, std::vector<Cursor>, std::greater<Cursor>> queue(std::greater<Cursor>{}, std::move(storage));
        std::vector<Event> out; out.reserve(count_);
        while (!queue.empty()) {
            const auto [ts, feed, seq, pos] = queue.top(); queue.pop();
            (void)ts; (void)seq;
            const auto& rows = feeds_[feed];
            out.push_back(rows[pos]);
            if (pos + 1 < rows.size()) {
                const auto& next = rows[pos + 1];
                queue.emplace(next.available_ns, feed, next.seq, pos + 1);
            }
        }
        return out;
    }
};
} // namespace qsl
