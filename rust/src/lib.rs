//! Availability-time ordered replay. Synthetic/academic component, not an OMS.
use std::cmp::Reverse;
use std::collections::BinaryHeap;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Event {
    pub available_ns: u64,
    pub feed: u64,
    pub seq: u64,
    pub venue_ns: i64,
    pub price_ticks: i64,
    pub qty: i64,
}
impl Event {
    fn key(&self) -> (u64, u64, u64) { (self.available_ns, self.feed, self.seq) }
}
pub struct Replay { feeds: Vec<Vec<Event>>, count: usize }
impl Replay {
    pub fn new(feeds: Vec<Vec<Event>>) -> Result<Self, &'static str> {
        let mut count = 0usize;
        for (f, rows) in feeds.iter().enumerate() {
            count = count.checked_add(rows.len()).ok_or("event count overflow")?;
            for (i, e) in rows.iter().enumerate() {
                if e.feed != f as u64 { return Err("feed mismatch"); }
                if i > 0 && (e.available_ns < rows[i-1].available_ns || e.seq <= rows[i-1].seq) {
                    return Err("non-monotone feed or sequence");
                }
            }
        }
        Ok(Self { feeds, count })
    }
    pub fn len(&self) -> usize { self.count }
    pub fn is_empty(&self) -> bool { self.count == 0 }
    pub fn reference(&self) -> Vec<Event> {
        let mut out = Vec::with_capacity(self.count);
        for rows in &self.feeds { out.extend(rows.iter().cloned()); }
        out.sort_by_key(Event::key);
        out
    }
    pub fn scan(&self) -> Vec<Event> {
        let mut out = Vec::with_capacity(self.count);
        let mut pos = vec![0usize; self.feeds.len()];
        while out.len() < self.count {
            let mut best: Option<usize> = None;
            for (f, rows) in self.feeds.iter().enumerate() {
                if pos[f] == rows.len() { continue; }
                if best.map_or(true, |b| rows[pos[f]].key() < self.feeds[b][pos[b]].key()) { best = Some(f); }
            }
            let f = best.expect("validated total count must have an available head");
            out.push(self.feeds[f][pos[f]].clone()); pos[f] += 1;
        }
        out
    }
    pub fn heap_replace(&self) -> Vec<Event> {
        let mut queue = BinaryHeap::with_capacity(self.feeds.len());
        let mut out = Vec::with_capacity(self.count);
        for (f, rows) in self.feeds.iter().enumerate() {
            if let Some(e) = rows.first() { queue.push(Reverse((e.available_ns,e.feed,e.seq,f,0usize))); }
        }
        while let Some(mut root) = queue.peek_mut() {
            let Reverse((_,_,_,f,p)) = *root;
            out.push(self.feeds[f][p].clone());
            if let Some(e) = self.feeds[f].get(p+1) {
                *root = Reverse((e.available_ns,e.feed,e.seq,f,p+1));
            } else {
                std::collections::binary_heap::PeekMut::pop(root);
            }
        }
        out
    }
    pub fn heap(&self) -> Vec<Event> {
        let mut queue = BinaryHeap::with_capacity(self.feeds.len());
        let mut out = Vec::with_capacity(self.count);
        for (f, rows) in self.feeds.iter().enumerate() {
            if let Some(e) = rows.first() { queue.push(Reverse((e.available_ns, e.feed, e.seq, f, 0usize))); }
        }
        while let Some(Reverse((_, _, _, f, p))) = queue.pop() {
            out.push(self.feeds[f][p].clone());
            if let Some(e) = self.feeds[f].get(p + 1) { queue.push(Reverse((e.available_ns, e.feed, e.seq, f, p+1))); }
        }
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn event(ts: u64, f: u64, seq: u64) -> Event { Event { available_ns: ts, feed:f, seq, venue_ns:-1, price_ticks:100, qty:1 } }
    #[test]
    fn differential() {
        for n in 0..200usize {
            let feeds = (0..n%33).map(|f| (0..(n*17+f*7)%150)
                .map(|i| event((i/3) as u64, f as u64, i as u64)).collect()).collect();
            let r = Replay::new(feeds).unwrap();
            assert_eq!(r.reference(), r.scan()); assert_eq!(r.reference(), r.heap()); assert_eq!(r.reference(), r.heap_replace());
        }
    }
    #[test]
    fn invalid_inputs() {
        assert!(Replay::new(vec![vec![event(2,0,0),event(1,0,1)]]).is_err());
        assert!(Replay::new(vec![vec![event(1,0,0),event(1,0,0)]]).is_err());
        assert!(Replay::new(vec![vec![event(1,1,0)]]).is_err());
    }
    #[test]
    fn integer_limits() {
        let r = Replay::new(vec![vec![event(u64::MAX,0,u64::MAX)],vec![event(u64::MAX,1,0)]]).unwrap();
        assert_eq!(r.heap(),r.reference());
    }
    #[test]
    fn bounded_channel_delivers_each_item_once() {
        // Standard-library blocking reference, not a custom lock-free queue.
        let (tx, rx) = std::sync::mpsc::sync_channel(7);
        let handles: Vec<_> = (0..4).map(|p| { let tx = tx.clone(); std::thread::spawn(move || {
            for i in 0..10000 { tx.send(p*10000+i).unwrap(); }
        }) }).collect();
        drop(tx);
        let mut seen = vec![0usize;40000];
        for item in rx { seen[item] += 1; }
        for h in handles { h.join().unwrap(); }
        assert!(seen.iter().all(|n| *n==1));
    }
    #[test]
    fn dropping_receiver_unblocks_sender_with_error() {
        let (tx,rx) = std::sync::mpsc::sync_channel(1);
        tx.send(1).unwrap();
        let handle = std::thread::spawn(move || tx.send(2).is_err());
        drop(rx); assert!(handle.join().unwrap());
    }
}
