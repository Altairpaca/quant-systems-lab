#include "replay.hpp"
#include "bounded_queue.hpp"
#include <atomic>
#include <chrono>
#include <fstream>
#include <iostream>
#include <random>
#include <sstream>
#include <string>
#include <thread>

using qsl::Event; using qsl::Feeds; using qsl::Replay;
void require(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
Feeds load(const std::string& file) {
    std::ifstream input(file); if (!input) throw std::runtime_error("cannot open fixture");
    Feeds feeds; std::string line; std::size_t line_no = 0;
    while (std::getline(input, line)) {
        ++line_no; if (line.empty() || line[0] == '#') continue;
        std::istringstream row(line); Event e{}; std::string extra;
        // Parse unsigned fields strictly: stream extraction alone accepts negative text.
        std::string ts, feed, seq;
        if (!(row >> ts >> feed >> seq >> e.venue_ns >> e.price_ticks >> e.qty) || (row >> extra))
            throw std::runtime_error("bad fixture row " + std::to_string(line_no));
        auto unsigned_value = [](const std::string& text) {
            if (text.empty() || text.find_first_not_of("0123456789") != std::string::npos)
                throw std::invalid_argument("invalid unsigned field");
            std::size_t n = 0; auto value = std::stoull(text, &n);
            if (n != text.size()) throw std::invalid_argument("invalid unsigned field");
            return static_cast<std::uint64_t>(value);
        };
        e.available_ns = unsigned_value(ts); e.feed = unsigned_value(feed); e.seq = unsigned_value(seq);
        if (e.feed > 4095) throw std::runtime_error("fixture feed id exceeds safety bound");
        if (feeds.size() <= e.feed) feeds.resize(e.feed + 1);
        feeds[e.feed].push_back(e);
    }
    if (input.bad()) throw std::runtime_error("fixture read failed");
    return feeds;
}
void print(const std::vector<Event>& rows) {
    for (auto& e : rows) std::cout << e.available_ns << '\t' << e.feed << '\t' << e.seq << '\t'
        << e.venue_ns << '\t' << e.price_ticks << '\t' << e.qty << '\n';
}
void tests() {
    std::mt19937_64 rng(1701);
    for (std::size_t c = 0; c < 200; ++c) {
        Feeds feeds(c % 33);
        for (std::size_t f = 0; f < feeds.size(); ++f) {
            std::uint64_t t = 0;
            for (std::size_t i = 0, n = rng() % 150; i < n; ++i) {
                t += rng() % 4;
                feeds[f].push_back({t, f, i, static_cast<std::int64_t>(t)-10, 100+static_cast<std::int64_t>(rng()%5), 1});
            }
        }
        Replay r(std::move(feeds)); auto oracle = r.reference();
        require(r.scan() == oracle && r.heap() == oracle && r.heap_replace() == oracle, "differential replay failed");
    }
    auto invalid = [](Feeds data) { bool rejected = false;
        try { Replay r(std::move(data)); } catch (const std::invalid_argument&) { rejected = true; }
        require(rejected, "invalid feed accepted"); };
    invalid({{{1,0,1,0,1,1},{0,0,2,0,1,1}}});
    invalid({{{1,0,1,0,1,1},{1,0,1,0,1,1}}});
    invalid({{{1,1,1,0,1,1}}});
    Replay extreme({{{UINT64_MAX,0,UINT64_MAX,INT64_MIN,INT64_MAX,-1}},{{UINT64_MAX,1,0,0,0,0}}});
    require(extreme.heap_replace() == extreme.reference() && extreme.heap() == extreme.reference(), "integer limits");
    qsl::BoundedQueue<std::uint64_t> queue(7);
    std::vector<std::thread> producers, consumers;
    std::mutex seen_mutex; std::vector<unsigned> seen(40000);
    for (unsigned i = 0; i < 2; ++i) consumers.emplace_back([&] {
        while (auto x = queue.pop()) { std::lock_guard lock(seen_mutex); ++seen.at(*x); }
    });
    for (unsigned p = 0; p < 4; ++p) producers.emplace_back([&,p] {
        for (unsigned n = 0; n < 10000; ++n) require(queue.push(p*10000+n), "premature close");
    });
    for (auto& t : producers) t.join();
    queue.close();
    for (auto& t : consumers) t.join();
    require(std::all_of(seen.begin(),seen.end(),[](auto n){ return n==1; }), "lost/duplicate queue item");
    require(!queue.push(1) && !queue.pop(), "close contract");
    qsl::BoundedQueue<int> full(1); require(full.push(1), "first push");
    std::atomic<bool> rejected{false};
    std::thread writer([&] { rejected = !full.push(2); });
    require(full.cancel() == 1, "cancel discard count"); writer.join();
    require(rejected && !full.pop(), "cancel must reject and unblock producer");
    qsl::BoundedQueue<int> empty(1); std::atomic<bool> ended{false};
    std::thread reader([&]{ ended = !empty.pop(); }); empty.close(); reader.join();
    require(ended, "close must wake consumer");
    std::cout << "PASS: 200 replay differential cases; invalid/limit cases; 4-producer/2-consumer exact delivery; close/cancel\n";
}
int main(int argc, char** argv) {
    try {
        if (argc == 2 && std::string(argv[1]) == "test") { tests(); return 0; }
        if (argc < 3) throw std::runtime_error("usage: qsl test | qsl dump FIXTURE [sort|scan|heap|heap-replace] | qsl bench FIXTURE");
        Replay r(load(argv[2]));
        std::vector<std::string> methods{"sort", "scan", "heap", "heap-replace"};
        auto run = [&](const std::string& method) {
            if (method == "sort") return r.reference();
            if (method == "scan") return r.scan();
            if (method == "heap") return r.heap();
            if (method == "heap-replace") return r.heap_replace();
            throw std::invalid_argument("unknown method");
        };
        if (std::string(argv[1]) == "dump") { print(run(argc > 3 ? argv[3] : "heap")); return 0; }
        if (std::string(argv[1]) != "bench") throw std::invalid_argument("unknown mode");
        auto expected = r.reference(); require(r.size() > 0, "benchmark fixture must be nonempty");
        for (int warm = 0; warm < 2; ++warm) for (auto& method : methods) require(run(method) == expected, "warm-up mismatch");
        std::mt19937 rng(20260912);
        std::cout << "repetition,method,events,elapsed_ns\n";
        for (int rep = 0; rep < 9; ++rep) {
            std::shuffle(methods.begin(), methods.end(), rng);
            for (auto& method : methods) {
                auto start = std::chrono::steady_clock::now(); auto out = run(method);
                auto stop = std::chrono::steady_clock::now();
                require(out == expected, "benchmark correctness mismatch");
                auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(stop-start).count();
                std::cout << rep << ',' << method << ',' << out.size() << ',' << ns << '\n';
            }
        }
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
