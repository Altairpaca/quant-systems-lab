//! L2 book-state replay consumer; protocol in docs/BOOK_CONSUMER.md.
use std::collections::BTreeMap;

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Side {
    Bid,
    Ask,
    Reset,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct BookEvent {
    pub available_ns: u64,
    pub feed: u64,
    pub session: u64,
    pub seq: u64,
    pub venue_ns: i64,
    pub side: Side,
    pub price_ticks: i64,
    pub qty: u64,
    pub line: usize,
}

impl BookEvent {
    fn key(&self) -> (u64, u64, u64, u64) {
        (self.available_ns, self.feed, self.session, self.seq)
    }
}

#[derive(Debug)]
pub enum BookError {
    Malformed { line: usize, message: String },
    Protocol { feed: u64, session: u64, line: usize, message: String },
}

impl BookError {
    pub fn exit_code(&self) -> u8 {
        match self {
            BookError::Malformed { .. } => 2,
            BookError::Protocol { .. } => 4,
        }
    }

    fn malformed(line: usize, message: impl Into<String>) -> Self {
        BookError::Malformed { line, message: message.into() }
    }

    fn protocol(e: &BookEvent, message: impl Into<String>) -> Self {
        BookError::Protocol { feed: e.feed, session: e.session, line: e.line, message: message.into() }
    }
}

impl std::fmt::Display for BookError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            BookError::Malformed { line, message } => {
                write!(f, "malformed fixture: row {line} {message}")
            }
            BookError::Protocol { feed, session, line, message } => write!(
                f,
                "protocol violation: feed {feed} session {session} {message} (line {line})"
            ),
        }
    }
}

impl std::error::Error for BookError {}

fn unsigned(text: &str) -> Option<u64> {
    if text.is_empty() || !text.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    text.parse().ok()
}

pub fn parse_fixture(text: &str) -> Result<Vec<BookEvent>, BookError> {
    let mut events = Vec::new();
    for (index, line) in text.lines().enumerate() {
        let line_no = index + 1;
        if line.trim().is_empty() || line.starts_with('#') {
            continue;
        }
        let fields: Vec<&str> = line.split_whitespace().collect();
        if fields.len() != 8 {
            return Err(BookError::malformed(
                line_no,
                format!("has {} columns, expected 8", fields.len()),
            ));
        }
        let available_ns = unsigned(fields[0]);
        let feed = unsigned(fields[1]);
        let session = unsigned(fields[2]);
        let seq = unsigned(fields[3]);
        let qty = unsigned(fields[7]);
        let (available_ns, feed, session, seq, qty) = match (available_ns, feed, session, seq, qty) {
            (Some(a), Some(fd), Some(s), Some(q), Some(v)) => (a, fd, s, q, v),
            _ => {
                return Err(BookError::malformed(
                    line_no,
                    "has a non-integer or out-of-range unsigned field",
                ))
            }
        };
        let venue_ns = match fields[4].parse::<i64>() {
            Ok(value) => value,
            Err(_) => return Err(BookError::malformed(line_no, "has a non-integer venue_ns field")),
        };
        let side = match fields[5] {
            "B" => Side::Bid,
            "A" => Side::Ask,
            "R" => Side::Reset,
            other => return Err(BookError::malformed(line_no, format!("invalid side {other}"))),
        };
        let price_ticks = match fields[6].parse::<i64>() {
            Ok(value) => value,
            Err(_) => return Err(BookError::malformed(line_no, "has a non-integer price field")),
        };
        if price_ticks < 0 {
            return Err(BookError::malformed(line_no, "has a negative price"));
        }
        if feed > 4095 {
            return Err(BookError::malformed(line_no, "feed exceeds 4095"));
        }
        if side == Side::Reset && (price_ticks != 0 || qty != 0) {
            return Err(BookError::malformed(
                line_no,
                "reset event must carry price 0 and qty 0",
            ));
        }
        events.push(BookEvent { available_ns, feed, session, seq, venue_ns, side, price_ticks, qty, line: line_no });
    }
    Ok(events)
}

struct FeedBook {
    session: Option<u64>,
    expected_seq: u64,
    bids: BTreeMap<i64, u64>,
    asks: BTreeMap<i64, u64>,
}

impl FeedBook {
    fn new() -> Self {
        Self { session: None, expected_seq: 0, bids: BTreeMap::new(), asks: BTreeMap::new() }
    }

    fn clear(&mut self) {
        self.bids.clear();
        self.asks.clear();
    }

    fn render(&self) -> String {
        let best_bid = self.bids.iter().next_back().map(|(p, q)| (*p, *q));
        let best_ask = self.asks.iter().next().map(|(p, q)| (*p, *q));
        let bids = levels(self.bids.iter().rev());
        let asks = levels(self.asks.iter());
        format!(
            "{}\t{}\t{}\t{}\t{}\t{}",
            best_bid.map_or(-1, |(p, _)| p),
            best_bid.map_or(0, |(_, q)| q),
            best_ask.map_or(-1, |(p, _)| p),
            best_ask.map_or(0, |(_, q)| q),
            bids,
            asks,
        )
    }
}

fn levels<'a>(iter: impl Iterator<Item = (&'a i64, &'a u64)>) -> String {
    let text: Vec<String> = iter.map(|(price, qty)| format!("{price}:{qty}")).collect();
    if text.is_empty() {
        "-".to_string()
    } else {
        text.join(",")
    }
}

pub struct BookReplay {
    feeds: BTreeMap<u64, FeedBook>,
    last_available_ns: BTreeMap<u64, u64>,
}

impl BookReplay {
    pub fn new() -> Self {
        Self { feeds: BTreeMap::new(), last_available_ns: BTreeMap::new() }
    }

    pub fn apply(&mut self, e: &BookEvent) -> Result<String, BookError> {
        if let Some(previous) = self.last_available_ns.get(&e.feed) {
            if e.available_ns < *previous {
                return Err(BookError::protocol(
                    e,
                    format!("available_ns decreased: {} -> {}", previous, e.available_ns),
                ));
            }
        }
        self.last_available_ns.insert(e.feed, e.available_ns);
        let book = self.feeds.entry(e.feed).or_insert_with(FeedBook::new);
        let mut kind = "U";
        match book.session {
            None => book.session = Some(e.session),
            Some(current) if e.session > current => {
                book.clear();
                book.session = Some(e.session);
                kind = "B";
            }
            Some(current) if e.session < current => {
                return Err(BookError::protocol(e, format!("session decrease: {current} -> {}", e.session)));
            }
            Some(_) if e.seq != book.expected_seq => {
                let name = if e.seq > book.expected_seq { "gap" } else { "out-of-order or duplicate" };
                return Err(BookError::protocol(
                    e,
                    format!("{name}: expected seq {}, got {}", book.expected_seq, e.seq),
                ));
            }
            Some(_) => {}
        }
        match e.side {
            Side::Reset => {
                book.clear();
                if kind != "B" {
                    kind = "R";
                }
            }
            Side::Bid => {
                if e.qty == 0 {
                    book.bids.remove(&e.price_ticks);
                } else {
                    book.bids.insert(e.price_ticks, e.qty);
                }
            }
            Side::Ask => {
                if e.qty == 0 {
                    book.asks.remove(&e.price_ticks);
                } else {
                    book.asks.insert(e.price_ticks, e.qty);
                }
            }
        }
        book.expected_seq = e.seq + 1;
        Ok(format!("{kind}\t{}", book.render()))
    }
}

impl Default for BookReplay {
    fn default() -> Self {
        Self::new()
    }
}

pub fn replay(events: &mut [BookEvent]) -> Result<Vec<String>, BookError> {
    let mut last_available: BTreeMap<u64, u64> = BTreeMap::new();
    for event in events.iter() {
        if let Some(previous) = last_available.get(&event.feed) {
            if event.available_ns < *previous {
                return Err(BookError::protocol(
                    event,
                    format!("available_ns decreased: {} -> {}", previous, event.available_ns),
                ));
            }
        }
        last_available.insert(event.feed, event.available_ns);
    }
    events.sort_by_key(BookEvent::key);
    let mut state = BookReplay::new();
    let mut lines = Vec::with_capacity(events.len());
    for (index, event) in events.iter().enumerate() {
        lines.push(format!("{index}\t{}\t{}", event.feed, event.session));
        let rendered = state.apply(event)?;
        let last = lines.last_mut().expect("just pushed");
        last.push('\t');
        last.push_str(&format!("{}\t{}", event.seq, rendered));
    }
    Ok(lines)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn parse(text: &str) -> Vec<BookEvent> {
        parse_fixture(text).expect("fixture must parse")
    }

    fn run(text: &str) -> Result<Vec<String>, BookError> {
        let mut events = parse_fixture(text)?;
        replay(&mut events)
    }

    fn failure(text: &str) -> BookError {
        run(text).expect_err("fixture must be rejected")
    }

    #[test]
    fn applies_updates_and_removes_zero_quantity() {
        let lines = run("0 0 0 0 0 B 100 5\n1 0 0 1 0 B 101 7\n2 0 0 2 0 B 100 0\n").unwrap();
        assert_eq!(lines[0], "0\t0\t0\t0\tU\t100\t5\t-1\t0\t100:5\t-");
        assert_eq!(lines[1], "1\t0\t0\t1\tU\t101\t7\t-1\t0\t101:7,100:5\t-");
        assert_eq!(lines[2], "2\t0\t0\t2\tU\t101\t7\t-1\t0\t101:7\t-");
    }

    #[test]
    fn sorts_both_sides_and_reports_bbo() {
        let lines = run("0 0 0 0 0 B 100 5\n0 0 0 1 0 B 102 3\n0 0 0 2 0 A 105 4\n0 0 0 3 0 A 103 1\n").unwrap();
        assert_eq!(lines[3], "3\t0\t0\t3\tU\t102\t3\t103\t1\t102:3,100:5\t103:1,105:4");
    }

    #[test]
    fn session_boundary_clears_and_marks_b() {
        let lines = run("0 0 0 0 0 B 100 5\n1 0 1 0 0 A 200 9\n").unwrap();
        assert_eq!(lines[1], "1\t0\t1\t0\tB\t-1\t0\t200\t9\t-\t200:9");
    }

    #[test]
    fn explicit_reset_clears_and_marks_r() {
        let lines = run("0 0 0 0 0 B 100 5\n1 0 0 1 0 R 0 0\n").unwrap();
        assert_eq!(lines[1], "1\t0\t0\t1\tR\t-1\t0\t-1\t0\t-\t-");
    }

    #[test]
    fn protocol_violations_are_rejected() {
        for fixture in [
            "0 0 0 0 0 B 100 5\n1 0 0 2 0 B 100 6\n",
            "0 0 0 0 0 B 100 5\n1 0 0 0 0 B 100 6\n",
            "0 0 1 0 0 B 100 5\n1 0 0 0 0 B 100 6\n",
        ] {
            assert!(matches!(failure(fixture), BookError::Protocol { .. }));
        }
        let decreased = failure("5 0 0 0 0 B 100 5\n4 0 0 1 0 B 100 6\n");
        assert!(matches!(decreased, BookError::Protocol { .. }));
        assert!(decreased.to_string().contains("available_ns decreased"));
    }

    #[test]
    fn malformed_rows_are_rejected() {
        assert!(matches!(failure("0 0 0 0 0 B 100\n"), BookError::Malformed { .. }));
        assert!(matches!(failure("0 0 0 x 0 B 100 5\n"), BookError::Malformed { .. }));
        assert!(matches!(failure("0 0 0 0 0 X 100 5\n"), BookError::Malformed { .. }));
        assert!(matches!(failure("0 0 0 0 0 B -1 5\n"), BookError::Malformed { .. }));
        assert!(matches!(failure("0 0 0 0 0 R 100 5\n"), BookError::Malformed { .. }));
        assert!(matches!(failure("0 4096 0 0 0 B 100 5\n"), BookError::Malformed { .. }));
        assert!(matches!(failure("18446744073709551616 0 0 0 0 B 100 5\n"), BookError::Malformed { .. }));
    }

    #[test]
    fn integer_limits_round_trip() {
        let lines = run("18446744073709551615 0 18446744073709551615 0 -9223372036854775808 B 9223372036854775807 18446744073709551615\n").unwrap();
        assert_eq!(lines[0], "0\t0\t18446744073709551615\t0\tU\t9223372036854775807\t18446744073709551615\t-1\t0\t9223372036854775807:18446744073709551615\t-");
    }

    #[test]
    fn multiple_feeds_merge_by_key() {
        let lines = run("10 1 0 0 0 B 100 1\n5 0 0 0 0 A 200 2\n").unwrap();
        assert_eq!(lines[0].split('\t').take(4).collect::<Vec<_>>(), vec!["0", "0", "0", "0"]);
        assert_eq!(lines[1].split('\t').take(4).collect::<Vec<_>>(), vec!["1", "1", "0", "0"]);
    }
}
