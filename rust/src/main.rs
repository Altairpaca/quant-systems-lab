use quant_systems_lab::book;
use quant_systems_lab::{Event, Replay};
use std::error::Error;
use std::io::{self, Write};
fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<String> = std::env::args().collect();
    if args.get(1).map(String::as_str) == Some("book") {
        return book_command(&args);
    }
    if args.len() < 3 { return Err("usage: qsl-rust dump FIXTURE [sort|scan|heap|heap-replace] | qsl-rust book FIXTURE".into()); }
    if args[1] != "dump" { return Err("unknown subcommand; expected dump or book".into()); }
    let mut feeds: Vec<Vec<Event>> = Vec::new();
    for (line_no,line) in std::fs::read_to_string(&args[2])?.lines().enumerate() {
        if line.is_empty() || line.starts_with('#') { continue; }
        let fields: Vec<_> = line.split_whitespace().collect();
        if fields.len() != 6 { return Err(format!("bad fixture row {}", line_no+1).into()); }
        let unsigned = |text: &str| -> Result<u64, Box<dyn Error>> {
            if text.is_empty() || !text.bytes().all(|b| b.is_ascii_digit()) { return Err("invalid unsigned field".into()); }
            Ok(text.parse()?)
        };
        let e = Event {available_ns: unsigned(fields[0])?, feed: unsigned(fields[1])?, seq: unsigned(fields[2])?,
            venue_ns:fields[3].parse()?, price_ticks:fields[4].parse()?, qty:fields[5].parse()?};
        if e.feed > 4095 { return Err("fixture feed id exceeds safety bound".into()); }
        if feeds.len() <= e.feed as usize { feeds.resize_with(e.feed as usize+1,Vec::new); }
        feeds[e.feed as usize].push(e);
    }
    let replay = Replay::new(feeds)?;
    let out = match args.get(3).map(String::as_str).unwrap_or("heap") {
        "sort" => replay.reference(), "scan" => replay.scan(), "heap" => replay.heap(), "heap-replace" => replay.heap_replace(),
        _ => return Err("unknown method".into())
    };
    let stdout = io::stdout(); let mut writer = io::BufWriter::new(stdout.lock());
    for e in out { writeln!(writer,"{}\t{}\t{}\t{}\t{}\t{}",e.available_ns,e.feed,e.seq,e.venue_ns,e.price_ticks,e.qty)?; }
    writer.flush()?; Ok(())
}

fn book_command(args: &[String]) -> Result<(), Box<dyn Error>> {
    if args.len() != 3 {
        eprintln!("usage: qsl-rust book FIXTURE");
        std::process::exit(2);
    }
    let text = match std::fs::read_to_string(&args[2]) {
        Ok(text) => text,
        Err(error) => {
            eprintln!("usage error: cannot read {}: {error}", args[2]);
            std::process::exit(2);
        }
    };
    let mut events = match book::parse_fixture(&text) {
        Ok(events) => events,
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(i32::from(error.exit_code()));
        }
    };
    let lines = match book::replay(&mut events) {
        Ok(lines) => lines,
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(i32::from(error.exit_code()));
        }
    };
    let stdout = io::stdout();
    let mut writer = io::BufWriter::new(stdout.lock());
    for line in lines { writeln!(writer, "{line}")?; }
    writer.flush()?;
    Ok(())
}
