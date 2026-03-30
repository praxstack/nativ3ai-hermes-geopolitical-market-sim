#![allow(dead_code)]

use std::{
    collections::BTreeSet,
    env, fs, io,
    path::{Path, PathBuf},
    process::{Command, Stdio},
    thread::sleep,
    time::{Duration, Instant},
};

use anyhow::{Context, Result};
use crossterm::{
    event::{self, Event, KeyCode, KeyEventKind},
    execute,
    terminal::{EnterAlternateScreen, LeaveAlternateScreen, disable_raw_mode, enable_raw_mode},
};
use ratatui::{
    DefaultTerminal, Frame,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span, Text},
    widgets::{Block, Borders, List, ListItem, ListState, Paragraph, Tabs, Wrap},
};
use serde::Deserialize;

#[derive(Debug, Clone, Deserialize)]
struct IndexFile {
    compiled_at: String,
    topic_count: usize,
    run_count: usize,
    branch_count: usize,
    topics: Vec<TopicSummary>,
    runs: Vec<RunSummary>,
    branches: Vec<BranchSummary>,
}

#[derive(Debug, Clone, Deserialize)]
struct TopicSummary {
    topic_id: String,
    run_count: usize,
    latest_run_id: String,
    latest_call: String,
    latest_confidence: f64,
    latest_market_yes_probability: f64,
    latest_predicted_yes_probability: f64,
    dominant_theme: String,
    accountability_path: String,
}

#[derive(Debug, Clone, Deserialize)]
struct RunSummary {
    topic_id: String,
    topic: String,
    run_id: String,
    generated_at: String,
    market_question: String,
    market_yes_probability: f64,
    predicted_yes_probability: f64,
    call: String,
    confidence: f64,
    dominant_theme: String,
    simulation_status: String,
    artifact_paths: ArtifactPaths,
}

#[derive(Debug, Clone, Deserialize)]
struct ArtifactPaths {
    decision: String,
    evidence: String,
    alerts: String,
    branch: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
struct DecisionArtifact {
    topic_id: String,
    topic: String,
    generated_at: String,
    market: MarketSection,
    signals: SignalsSection,
    simulation: SimulationSection,
    forecast: ForecastSection,
    branch: Option<BranchSummary>,
}

#[derive(Debug, Clone, Deserialize)]
struct MarketSection {
    question: String,
    url: String,
    deadline_display: String,
    #[serde(default)]
    market_close_display: String,
    best_bid: f64,
    best_ask: f64,
    yes_probability: f64,
    spread: f64,
    volume: f64,
    liquidity: f64,
    resolution_notes: String,
}

#[derive(Debug, Clone, Deserialize)]
struct SignalsSection {
    headline_count: usize,
    dominant_theme: String,
    #[serde(default)]
    top_themes: Vec<ThemeCount>,
    risk_average: f64,
    #[serde(default)]
    actor_candidates: Vec<ActorCount>,
    #[serde(default)]
    module_set: Vec<String>,
    official_source_count: usize,
    #[serde(default)]
    finding_count: Option<usize>,
}

#[derive(Debug, Clone, Deserialize)]
struct ThemeCount {
    theme: String,
    count: usize,
}

#[derive(Debug, Clone, Deserialize)]
struct ActorCount {
    label: String,
    count: usize,
}

#[derive(Debug, Clone, Deserialize)]
struct SimulationSection {
    simulation_id: String,
    status: String,
    lines: usize,
    #[serde(default)]
    total_actions: usize,
    agent_count: usize,
    twitter_actions: usize,
    reddit_actions: usize,
    #[serde(default)]
    current_round: usize,
    #[serde(default)]
    total_rounds: usize,
    #[serde(default)]
    top_agents: Vec<(String, usize)>,
    #[serde(default)]
    theme_counts: std::collections::BTreeMap<String, usize>,
    #[serde(default)]
    action_counts: std::collections::BTreeMap<String, usize>,
    #[serde(default)]
    twitter_round_activity: Vec<usize>,
    #[serde(default)]
    reddit_round_activity: Vec<usize>,
    #[serde(default)]
    combined_round_activity: Vec<usize>,
    #[serde(default)]
    selected_entities: Vec<SelectedEntity>,
    #[serde(default)]
    admission_summary: AdmissionSummary,
}

#[derive(Debug, Clone, Deserialize, Default)]
struct SelectedEntity {
    name: String,
    role: String,
    score: f64,
    threshold: f64,
    rationale: String,
    #[serde(default)]
    graph_degree: usize,
    #[serde(default)]
    anchor_overlap: usize,
    #[serde(default)]
    summary_overlap: usize,
}

#[derive(Debug, Clone, Deserialize, Default)]
struct AdmissionSummary {
    candidate_count: usize,
    selected_count: usize,
    anchored_count: usize,
    rejected_count: usize,
    avg_score: f64,
}

#[derive(Debug, Clone, Deserialize)]
struct ForecastSection {
    market_yes_probability: f64,
    predicted_yes_probability: f64,
    edge: f64,
    confidence: f64,
    call: String,
    drivers: Vec<Driver>,
    invalidation: Vec<String>,
    thesis: String,
    why_now: String,
    operator_note: String,
}

#[derive(Debug, Clone, Deserialize)]
struct Driver {
    label: String,
    polarity: String,
    strength: f64,
    explanation: String,
    evidence_ids: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
struct EvidenceFile {
    evidence: Vec<EvidenceItem>,
}

#[derive(Debug, Clone, Deserialize)]
struct EvidenceItem {
    id: String,
    kind: String,
    title: String,
    source: String,
    url: String,
    timestamp: String,
    theme: String,
    credibility: String,
    impact: String,
}

#[derive(Debug, Clone, Deserialize)]
struct AlertsFile {
    alerts: Vec<Alert>,
}

#[derive(Debug, Clone, Deserialize)]
struct Alert {
    kind: String,
    level: String,
    message: String,
    delta: Option<f64>,
}

#[derive(Debug, Clone, Deserialize)]
struct AccountabilityFile {
    records: Vec<AccountabilityRecord>,
}

#[derive(Debug, Clone, Deserialize)]
struct AccountabilityRecord {
    run_id: String,
    generated_at: String,
    call: String,
    confidence: f64,
    market_yes_probability: f64,
    predicted_yes_probability: f64,
    edge: f64,
    dominant_theme: String,
    simulation_status: String,
}

#[derive(Debug, Clone, Deserialize)]
struct BranchSummary {
    enabled: Option<bool>,
    simulation_id: String,
    base_simulation_id: String,
    actor_name: Option<String>,
    entity_type: Option<String>,
    injection_round: Option<i64>,
    opening_statement: Option<String>,
    action_delta: Option<i64>,
    diplomacy_delta: Option<i64>,
    conflict_delta: Option<i64>,
    interpretation: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Focus {
    Topics,
    Runs,
    Branches,
    Tabs,
    Detail,
}

#[derive(Debug, Clone, Copy)]
enum DetailTab {
    Decision,
    Evidence,
    Alerts,
    Accountability,
    Branch,
}

impl DetailTab {
    fn all() -> [DetailTab; 5] {
        [
            DetailTab::Decision,
            DetailTab::Evidence,
            DetailTab::Alerts,
            DetailTab::Accountability,
            DetailTab::Branch,
        ]
    }

    fn title(self) -> &'static str {
        match self {
            DetailTab::Decision => "Decision",
            DetailTab::Evidence => "Evidence",
            DetailTab::Alerts => "Alerts",
            DetailTab::Accountability => "Accountability",
            DetailTab::Branch => "Branch",
        }
    }
}

struct App {
    data_root: PathBuf,
    index: IndexFile,
    compile_python: Option<PathBuf>,
    compile_script: Option<PathBuf>,
    compile_mirofish_root: Option<PathBuf>,
    auto_refresh_interval: Duration,
    last_refresh_at: Instant,
    topic_idx: usize,
    run_idx: usize,
    branch_idx: usize,
    focus: Focus,
    detail_tab: usize,
    detail_scroll: u16,
    tick: u64,
    footer_message: String,
    show_help: bool,
}

impl App {
    fn new(
        data_root: PathBuf,
        index: IndexFile,
        initial_topic_id: Option<&str>,
        compile_python: Option<PathBuf>,
        compile_script: Option<PathBuf>,
        compile_mirofish_root: Option<PathBuf>,
        auto_refresh_interval: Duration,
    ) -> Self {
        let mut app = Self {
            data_root,
            index,
            compile_python,
            compile_script,
            compile_mirofish_root,
            auto_refresh_interval,
            last_refresh_at: Instant::now(),
            topic_idx: 0,
            run_idx: 0,
            branch_idx: 0,
            focus: Focus::Topics,
            detail_tab: 0,
            detail_scroll: 0,
            tick: 0,
            footer_message: "control room armed".to_string(),
            show_help: false,
        };
        if let Some(topic_id) = initial_topic_id {
            if let Some(position) = app
                .index
                .topics
                .iter()
                .position(|topic| topic.topic_id == topic_id)
            {
                app.topic_idx = position;
            }
        }
        app.align_run_to_topic();
        app.select_latest_run();
        app.align_branch_to_topic();
        app
    }

    fn reload(&mut self) -> Result<()> {
        self.index = load_index(&self.data_root)?;
        if self.topic_idx >= self.index.topics.len() {
            self.topic_idx = self.index.topics.len().saturating_sub(1);
        }
        self.select_latest_run();
        self.align_branch_to_topic();
        self.detail_scroll = 0;
        Ok(())
    }

    fn refresh_from_source(&mut self) -> Result<bool> {
        let before_compiled_at = self.index.compiled_at.clone();
        let before_run_id = self.current_run().map(|run| run.run_id.clone());
        self.compile_index()?;
        self.reload()?;
        let changed = self.index.compiled_at != before_compiled_at
            || self.current_run().map(|run| run.run_id.clone()) != before_run_id;
        self.last_refresh_at = Instant::now();
        Ok(changed)
    }

    fn compile_index(&self) -> Result<()> {
        let Some(python) = self.compile_python.as_ref() else {
            return Ok(());
        };
        let Some(script) = self.compile_script.as_ref() else {
            return Ok(());
        };
        let Some(mirofish_root) = self.compile_mirofish_root.as_ref() else {
            return Ok(());
        };
        let status = Command::new(python)
            .arg(script)
            .arg("compile-artifacts")
            .arg("--mirofish-root")
            .arg(mirofish_root)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .with_context(|| format!("failed to run compile command via {}", python.display()))?;
        if !status.success() {
            anyhow::bail!("compile-artifacts exited with status {}", status);
        }
        Ok(())
    }

    fn current_topic(&self) -> Option<&TopicSummary> {
        self.index.topics.get(self.topic_idx)
    }

    fn topic_runs(&self) -> Vec<&RunSummary> {
        let Some(topic) = self.current_topic() else {
            return Vec::new();
        };
        self.index
            .runs
            .iter()
            .filter(|run| run.topic_id == topic.topic_id)
            .collect()
    }

    fn current_run(&self) -> Option<&RunSummary> {
        let runs = self.topic_runs();
        runs.get(self.run_idx).copied()
    }

    fn topic_branches(&self) -> Vec<&BranchSummary> {
        let simulation_ids: BTreeSet<String> = self
            .topic_runs()
            .into_iter()
            .filter_map(simulation_id_for_run)
            .collect();
        self.index
            .branches
            .iter()
            .filter(|branch| {
                simulation_ids.contains(&branch.simulation_id)
                    || simulation_ids.contains(&branch.base_simulation_id)
            })
            .collect()
    }

    fn current_branch(&self) -> Option<&BranchSummary> {
        let branches = self.topic_branches();
        branches.get(self.branch_idx).copied()
    }

    fn select_latest_run(&mut self) {
        let runs = self.topic_runs();
        if runs.is_empty() {
            self.run_idx = 0;
        } else {
            self.run_idx = runs.len() - 1;
        }
        self.align_branch_to_topic();
    }

    fn align_run_to_topic(&mut self) {
        let runs = self.topic_runs();
        if runs.is_empty() {
            self.run_idx = 0;
        } else if self.run_idx >= runs.len() {
            self.run_idx = runs.len() - 1;
        }
    }

    fn align_branch_to_topic(&mut self) {
        let branches = self.topic_branches();
        if branches.is_empty() {
            self.branch_idx = 0;
        } else if self.branch_idx >= branches.len() {
            self.branch_idx = branches.len() - 1;
        }
    }

    fn current_tab(&self) -> DetailTab {
        DetailTab::all()[self.detail_tab.min(DetailTab::all().len() - 1)]
    }

    fn cycle_focus(&mut self) {
        self.focus = match self.focus {
            Focus::Topics => Focus::Runs,
            Focus::Runs => Focus::Branches,
            Focus::Branches => Focus::Tabs,
            Focus::Tabs => Focus::Detail,
            Focus::Detail => Focus::Topics,
        };
    }
}

fn focus_label(focus: Focus) -> &'static str {
    match focus {
        Focus::Topics => "TOPICS",
        Focus::Runs => "RUNS",
        Focus::Branches => "BRANCHES",
        Focus::Tabs => "TABS",
        Focus::Detail => "DETAIL",
    }
}

fn spinner(tick: u64) -> &'static str {
    match tick % 4 {
        0 => "|",
        1 => "/",
        2 => "-",
        _ => "\\",
    }
}

fn pulse_bar(tick: u64, width: usize) -> String {
    if width == 0 {
        return String::new();
    }
    let pos = (tick as usize) % width;
    let mut chars = vec!['.'; width];
    chars[pos] = '#';
    if pos > 0 {
        chars[pos - 1] = '=';
    }
    if pos + 1 < width {
        chars[pos + 1] = '=';
    }
    chars.into_iter().collect()
}

fn confidence_bar(value: f64, width: usize) -> String {
    let clamped = value.clamp(0.0, 1.0);
    let filled = ((clamped * width as f64).round() as usize).min(width);
    format!(
        "[{}{}]",
        "#".repeat(filled),
        ".".repeat(width.saturating_sub(filled))
    )
}

fn simulation_progress_bar(current_round: usize, total_rounds: usize, width: usize) -> String {
    if width == 0 {
        return String::new();
    }
    if total_rounds == 0 {
        return ".".repeat(width);
    }
    let clamped = current_round.min(total_rounds);
    let filled = ((clamped as f64 / total_rounds as f64) * width as f64).round() as usize;
    format!(
        "{}{}",
        "#".repeat(filled.min(width)),
        ".".repeat(width.saturating_sub(filled.min(width)))
    )
}

fn meter(value: usize, max_value: usize, width: usize) -> String {
    if width == 0 {
        return String::new();
    }
    if max_value == 0 {
        return ".".repeat(width);
    }
    let filled = ((value as f64 / max_value as f64) * width as f64).round() as usize;
    format!(
        "{}{}",
        "#".repeat(filled.min(width)),
        ".".repeat(width.saturating_sub(filled.min(width)))
    )
}

fn sparkline(series: &[usize], width: usize) -> String {
    if width == 0 {
        return String::new();
    }
    if series.is_empty() {
        return ".".repeat(width);
    }
    let levels = ['.', ':', '-', '=', '+', '*', '#', '%', '@'];
    let step = (series.len() as f64 / width as f64).max(1.0);
    let mut reduced: Vec<usize> = Vec::with_capacity(width);
    let mut idx: f64 = 0.0;
    while reduced.len() < width {
        let start = idx.floor() as usize;
        let end = ((idx + step).ceil() as usize)
            .max(start + 1)
            .min(series.len());
        let chunk = &series[start.min(series.len() - 1)..end];
        let peak = chunk.iter().copied().max().unwrap_or(0);
        reduced.push(peak);
        idx += step;
        if end >= series.len() && reduced.len() >= width {
            break;
        }
        if end >= series.len() && reduced.len() < width {
            reduced.resize(width, peak);
            break;
        }
    }
    let max_value = reduced.iter().copied().max().unwrap_or(0);
    reduced
        .iter()
        .map(|value| {
            if max_value == 0 {
                '.'
            } else {
                let bucket = ((*value as f64 / max_value as f64) * (levels.len() - 1) as f64)
                    .round() as usize;
                levels[bucket.min(levels.len() - 1)]
            }
        })
        .collect()
}

fn probability_sparkline(values: &[f64], width: usize) -> String {
    if width == 0 {
        return String::new();
    }
    if values.is_empty() {
        return ".".repeat(width);
    }
    let ints: Vec<usize> = values
        .iter()
        .map(|value| ((*value).clamp(0.0, 1.0) * 1000.0).round() as usize)
        .collect();
    sparkline(&ints, width)
}

struct CliArgs {
    data_root: PathBuf,
    topic_id: Option<String>,
    compile_python: Option<PathBuf>,
    compile_script: Option<PathBuf>,
    compile_mirofish_root: Option<PathBuf>,
    auto_refresh_seconds: u64,
}

fn resolve_cli_args() -> CliArgs {
    let mut args = env::args().skip(1);
    let mut data_root = None;
    let mut topic_id = None;
    let mut compile_python = None;
    let mut compile_script = None;
    let mut compile_mirofish_root = None;
    let mut auto_refresh_seconds = 4_u64;
    while let Some(arg) = args.next() {
        if arg == "--data-root" {
            if let Some(value) = args.next() {
                data_root = Some(PathBuf::from(value));
            }
        } else if arg == "--topic-id" {
            if let Some(value) = args.next() {
                topic_id = Some(value);
            }
        } else if arg == "--compile-python" {
            if let Some(value) = args.next() {
                compile_python = Some(PathBuf::from(value));
            }
        } else if arg == "--compile-script" {
            if let Some(value) = args.next() {
                compile_script = Some(PathBuf::from(value));
            }
        } else if arg == "--compile-mirofish-root" {
            if let Some(value) = args.next() {
                compile_mirofish_root = Some(PathBuf::from(value));
            }
        } else if arg == "--auto-refresh-seconds" {
            if let Some(value) = args.next() {
                auto_refresh_seconds = value.parse::<u64>().unwrap_or(4).max(1);
            }
        }
    }
    let resolved_root = data_root.unwrap_or_else(|| {
        dirs::home_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join(".hermes")
            .join("data")
            .join("geopolitical-market-sim")
    });
    CliArgs {
        data_root: resolved_root,
        topic_id,
        compile_python,
        compile_script,
        compile_mirofish_root,
        auto_refresh_seconds,
    }
}

fn load_json<T: for<'de> Deserialize<'de>>(path: &Path) -> Result<T> {
    let raw =
        fs::read_to_string(path).with_context(|| format!("failed to read {}", path.display()))?;
    let data = serde_json::from_str::<T>(&raw)
        .with_context(|| format!("failed to parse {}", path.display()))?;
    Ok(data)
}

fn load_index(data_root: &Path) -> Result<IndexFile> {
    load_json(&data_root.join("compiled").join("index.json"))
}

fn decision_for_run(run: &RunSummary) -> Result<DecisionArtifact> {
    load_json(Path::new(&run.artifact_paths.decision))
}

fn evidence_for_run(run: &RunSummary) -> Result<EvidenceFile> {
    load_json(Path::new(&run.artifact_paths.evidence))
}

fn alerts_for_run(run: &RunSummary) -> Result<AlertsFile> {
    load_json(Path::new(&run.artifact_paths.alerts))
}

fn accountability_for_topic(topic: &TopicSummary) -> Result<AccountabilityFile> {
    load_json(Path::new(&topic.accountability_path))
}

fn branch_for_run(run: &RunSummary) -> Option<Result<BranchSummary>> {
    run.artifact_paths
        .branch
        .as_ref()
        .map(|path| load_json(Path::new(path)))
}

fn simulation_id_for_run(run: &RunSummary) -> Option<String> {
    let decision = decision_for_run(run).ok()?;
    let simulation_id = decision.simulation.simulation_id.trim();
    if simulation_id.is_empty() || simulation_id == "n/a" {
        None
    } else {
        Some(simulation_id.to_string())
    }
}

fn pct(value: f64) -> String {
    format!("{:.1}%", value * 100.0)
}

fn yes_no_pair(yes: f64) -> String {
    let no = (1.0 - yes).clamp(0.0, 1.0);
    format!("YES {} / NO {}", pct(yes), pct(no))
}

fn edge_pair(edge: f64) -> String {
    format!("YES {:+.1} pts / NO {:+.1} pts", edge * 100.0, -edge * 100.0)
}

fn call_style(call: &str) -> Style {
    match call {
        "YES" => Style::default()
            .fg(Color::Green)
            .add_modifier(Modifier::BOLD),
        "NO" => Style::default().fg(Color::Red).add_modifier(Modifier::BOLD),
        _ => Style::default()
            .fg(Color::Yellow)
            .add_modifier(Modifier::BOLD),
    }
}

fn focus_style(active: bool) -> Style {
    if active {
        Style::default()
            .fg(Color::Cyan)
            .add_modifier(Modifier::BOLD)
    } else {
        Style::default()
    }
}

fn render(frame: &mut Frame, app: &App) {
    let layout = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(7),
            Constraint::Min(12),
            Constraint::Length(4),
        ])
        .split(frame.area());

    render_header(frame, layout[0], app);
    render_body(frame, layout[1], app);
    render_footer(frame, layout[2], app);
    if app.show_help {
        render_help_overlay(frame);
    }
}

fn render_header(frame: &mut Frame, area: Rect, app: &App) {
    let topic = app.current_topic();
    let run = app.current_run();
    let phase = pulse_bar(app.tick, 16);
    let latest = topic
        .map(|row| {
            format!(
                "{} {} conf {:.0}% mkt {} mod {}",
                row.topic_id,
                row.latest_call,
                row.latest_confidence * 100.0,
                yes_no_pair(row.latest_market_yes_probability),
                yes_no_pair(row.latest_predicted_yes_probability)
            )
        })
        .unwrap_or_else(|| "no topics loaded".to_string());
    let art = [
        " ____  ____  _____ ____ ___ _   _ _____ ____  __  __ _____ ____",
        "|  _ \\|  _ \\| ____/ ___|_ _| | | | ____|  _ \\|  \\/  | ____/ ___|",
        "| |_) | |_) |  _|| |    | || |_| |  _| | |_) | |\\/| |  _| \\___ \\",
        "|  __/|  _ <| |__| |___ | ||  _  | |___|  _ <| |  | | |___ ___) |",
        "|_|   |_| \\_\\_____\\____|___|_| |_|_____|_| \\_\\_|  |_|_____|____/",
    ];
    let text = Paragraph::new(Text::from(vec![
        Line::from(Span::styled(
            art[(app.tick as usize / 2) % art.len()],
            Style::default()
                .fg(Color::Cyan)
                .add_modifier(Modifier::BOLD),
        )),
        Line::from(vec![
            Span::styled(
                "LOCAL CONTROL ROOM",
                Style::default()
                    .fg(Color::Yellow)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw("  "),
            Span::raw(format!(
                "focus {}  pulse {}  tick {}",
                focus_label(app.focus),
                phase,
                app.tick
            )),
        ]),
        Line::from(format!(
            "topics {}  runs {}  branches {}  compiled {}  :: {}",
            app.index.topic_count,
            app.index.run_count,
            app.index.branch_count,
            app.index.compiled_at,
            latest
        )),
        Line::from(
            run.map(|row| {
                format!(
                    "selected run {}  status {}  call {}  {}",
                    row.run_id,
                    row.simulation_status,
                    row.call,
                    yes_no_pair(row.predicted_yes_probability),
                )
            })
            .unwrap_or_else(|| "selected run n/a".to_string()),
        ),
    ]))
    .block(
        Block::default()
            .borders(Borders::ALL)
            .title(":: PREDIHERMES OVERWATCH ::"),
    );
    frame.render_widget(text, area);
}

fn render_body(frame: &mut Frame, area: Rect, app: &App) {
    let columns = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(18),
            Constraint::Percentage(22),
            Constraint::Percentage(20),
            Constraint::Percentage(40),
        ])
        .split(area);

    render_topics(frame, columns[0], app);
    render_runs(frame, columns[1], app);
    render_branches(frame, columns[2], app);
    render_detail(frame, columns[3], app);
}

fn render_topics(frame: &mut Frame, area: Rect, app: &App) {
    let items: Vec<ListItem> = app
        .index
        .topics
        .iter()
        .map(|topic| {
            let style = call_style(&topic.latest_call);
            ListItem::new(vec![
                Line::from(topic.topic_id.clone())
                    .style(Style::default().add_modifier(Modifier::BOLD)),
                Line::from(vec![
                    Span::styled(topic.latest_call.clone(), style),
                    Span::raw(format!(
                        "  conf {:.0}% {} runs {}",
                        topic.latest_confidence * 100.0,
                        confidence_bar(topic.latest_confidence, 6),
                        topic.run_count
                    )),
                ]),
                Line::from(shorten(&topic.dominant_theme, 26)),
            ])
        })
        .collect();
    let mut state = ListState::default().with_selected(Some(app.topic_idx));
    let list = List::new(items)
        .block(
            Block::default()
                .borders(Borders::ALL)
                .title(format!(
                    "{} TOPICS {}",
                    if app.focus == Focus::Topics {
                        ">>"
                    } else {
                        ".."
                    },
                    spinner(app.tick)
                ))
                .border_style(focus_style(app.focus == Focus::Topics)),
        )
        .highlight_style(Style::default().bg(Color::DarkGray))
        .highlight_symbol("» ");
    frame.render_stateful_widget(list, area, &mut state);
}

fn render_runs(frame: &mut Frame, area: Rect, app: &App) {
    let runs = app.topic_runs();
    let items: Vec<ListItem> = runs
        .iter()
        .map(|run| {
            ListItem::new(vec![
                Line::from(run.run_id.clone()).style(Style::default().add_modifier(Modifier::BOLD)),
                Line::from(vec![
                    Span::styled(run.call.clone(), call_style(&run.call)),
                    Span::raw(format!(
                        "  {}  mkt {}  mod {}  conf {:.0}% {}",
                        shorten(&run.simulation_status, 10),
                        yes_no_pair(run.market_yes_probability),
                        yes_no_pair(run.predicted_yes_probability),
                        run.confidence * 100.0,
                        confidence_bar(run.confidence, 6),
                    )),
                ]),
                Line::from(shorten(&run.generated_at, 30)),
            ])
        })
        .collect();
    let mut state = ListState::default().with_selected(Some(app.run_idx));
    let list = List::new(items)
        .block(
            Block::default()
                .borders(Borders::ALL)
                .title(format!(
                    "{} RUNS {}",
                    if app.focus == Focus::Runs { ">>" } else { ".." },
                    spinner(app.tick + 1)
                ))
                .border_style(focus_style(app.focus == Focus::Runs)),
        )
        .highlight_style(Style::default().bg(Color::DarkGray))
        .highlight_symbol("» ");
    frame.render_stateful_widget(list, area, &mut state);
}

fn render_branches(frame: &mut Frame, area: Rect, app: &App) {
    let branches = app.topic_branches();
    let items: Vec<ListItem> = branches
        .iter()
        .map(|branch| {
            let actor = branch
                .actor_name
                .clone()
                .unwrap_or_else(|| "n/a".to_string());
            let delta = branch.action_delta.unwrap_or(0);
            let diplomacy = branch.diplomacy_delta.unwrap_or(0);
            ListItem::new(vec![
                Line::from(actor).style(Style::default().add_modifier(Modifier::BOLD)),
                Line::from(format!(
                    "{}  base {}",
                    branch
                        .entity_type
                        .clone()
                        .unwrap_or_else(|| "n/a".to_string()),
                    shorten(&branch.base_simulation_id, 12)
                )),
                Line::from(format!(
                    "r{}  act {:+} dip {:+}",
                    branch.injection_round.unwrap_or_default(),
                    delta,
                    diplomacy
                )),
            ])
        })
        .collect();
    let empty = vec![ListItem::new(vec![
        Line::from("no branches"),
        Line::from("create one from a"),
        Line::from("completed base sim"),
    ])];
    let mut state = ListState::default().with_selected(Some(app.branch_idx));
    let list = List::new(if items.is_empty() { empty } else { items })
        .block(
            Block::default()
                .borders(Borders::ALL)
                .title(format!(
                    "{} BRANCHES {}",
                    if app.focus == Focus::Branches {
                        ">>"
                    } else {
                        ".."
                    },
                    spinner(app.tick + 3)
                ))
                .border_style(focus_style(app.focus == Focus::Branches)),
        )
        .highlight_style(Style::default().bg(Color::DarkGray))
        .highlight_symbol("» ");
    frame.render_stateful_widget(list, area, &mut state);
}

fn render_detail(frame: &mut Frame, area: Rect, app: &App) {
    let vertical = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(3), Constraint::Min(10)])
        .split(area);
    let tab_titles: Vec<Line> = DetailTab::all()
        .iter()
        .map(|tab| Line::from(tab.title()))
        .collect();
    let tabs = Tabs::new(tab_titles)
        .select(app.detail_tab)
        .block(
            Block::default()
                .borders(Borders::ALL)
                .title(format!(
                    "{} CONTROL DECK {}",
                    if app.focus == Focus::Tabs { ">>" } else { ".." },
                    spinner(app.tick + 2)
                ))
                .border_style(focus_style(app.focus == Focus::Tabs)),
        )
        .highlight_style(
            Style::default()
                .fg(Color::Yellow)
                .add_modifier(Modifier::BOLD),
        );
    frame.render_widget(tabs, vertical[0]);

    let body = match build_detail_text(app) {
        Ok(text) => text,
        Err(err) => Text::from(format!("failed to load detail: {err:#}")),
    };
    let paragraph = Paragraph::new(body)
        .block(
            Block::default()
                .borders(Borders::ALL)
                .title(format!(
                    "{} {} {}",
                    if app.focus == Focus::Detail {
                        ">>"
                    } else {
                        ".."
                    },
                    app.current_tab().title(),
                    confidence_bar(
                        app.current_run().map(|run| run.confidence).unwrap_or(0.0),
                        8
                    )
                ))
                .border_style(focus_style(app.focus == Focus::Detail)),
        )
        .wrap(Wrap { trim: false })
        .scroll((app.detail_scroll, 0));
    frame.render_widget(paragraph, vertical[1]);
}

fn build_detail_text(app: &App) -> Result<Text<'static>> {
    let Some(topic) = app.current_topic() else {
        return Ok(Text::from(
            "No topics compiled yet. Run compile-artifacts first.",
        ));
    };
    let Some(run) = app.current_run() else {
        return Ok(Text::from("No runs for the selected topic."));
    };
    match app.current_tab() {
        DetailTab::Decision => build_decision_text(run),
        DetailTab::Evidence => build_evidence_text(run),
        DetailTab::Alerts => build_alerts_text(run),
        DetailTab::Accountability => build_accountability_text(topic),
        DetailTab::Branch => build_branch_text(run, &app.index.branches, app.current_branch()),
    }
}

fn build_decision_text(run: &RunSummary) -> Result<Text<'static>> {
    let decision = decision_for_run(run)?;
    let total_actions = decision.simulation.total_actions.max(1);
    let total_rounds = decision
        .simulation
        .total_rounds
        .max(decision.simulation.current_round)
        .max(1);
    let top_theme_max = decision
        .signals
        .top_themes
        .first()
        .map(|row| row.count)
        .unwrap_or(1)
        .max(1);
    let top_agent_max = decision
        .simulation
        .top_agents
        .first()
        .map(|row| row.1)
        .unwrap_or(1)
        .max(1);
    let mut lines = vec![
        Line::from(vec![
            Span::styled(
                decision.forecast.call.clone(),
                call_style(&decision.forecast.call),
            ),
            Span::raw(format!(
                "  confidence {:.0}%  {}",
                decision.forecast.confidence * 100.0,
                confidence_bar(decision.forecast.confidence, 10),
            )),
        ]),
        Line::from(format!(
            "market      {}",
            yes_no_pair(decision.forecast.market_yes_probability),
        )),
        Line::from(format!(
            "predihermes {}",
            yes_no_pair(decision.forecast.predicted_yes_probability),
        )),
        Line::from(format!(
            "dislocation {}",
            edge_pair(decision.forecast.edge),
        )),
        Line::from(decision.forecast.thesis),
        Line::from(decision.forecast.why_now),
        Line::from(format!(
            "resolution {}  bid {} ask {} spread {:.3}",
            decision.market.deadline_display,
            pct(decision.market.best_bid),
            pct(decision.market.best_ask),
            decision.market.spread,
        )),
        Line::from(format!(
            "market close {}",
            decision.market.market_close_display,
        )),
        Line::from(format!(
            "signals headlines {} official {} findings {} risk {:.2} sim actions {} agents {}",
            decision.signals.headline_count,
            decision.signals.official_source_count,
            decision.signals.finding_count.unwrap_or(0),
            decision.signals.risk_average,
            decision.simulation.total_actions,
            decision.simulation.agent_count,
        )),
        Line::from(format!(
            "admission {} selected / {} candidates  anchored {}  rejected {}  avg {:.2}",
            decision.simulation.admission_summary.selected_count,
            decision.simulation.admission_summary.candidate_count,
            decision.simulation.admission_summary.anchored_count,
            decision.simulation.admission_summary.rejected_count,
            decision.simulation.admission_summary.avg_score,
        )),
        Line::from(format!(
            "simulation {:<10} round {}/{}  [{}]",
            decision.simulation.status,
            decision.simulation.current_round,
            total_rounds,
            simulation_progress_bar(decision.simulation.current_round, total_rounds, 28),
        )),
        Line::from(""),
        Line::from(Span::styled(
            "MiroFish Activity Graph",
            Style::default().add_modifier(Modifier::BOLD),
        )),
        Line::from(format!(
            "combined {}",
            sparkline(&decision.simulation.combined_round_activity, 44)
        )),
        Line::from(format!(
            "twitter  {}  {:>4} {}",
            sparkline(&decision.simulation.twitter_round_activity, 30),
            decision.simulation.twitter_actions,
            meter(decision.simulation.twitter_actions, total_actions, 10)
        )),
        Line::from(format!(
            "reddit   {}  {:>4} {}",
            sparkline(&decision.simulation.reddit_round_activity, 30),
            decision.simulation.reddit_actions,
            meter(decision.simulation.reddit_actions, total_actions, 10)
        )),
        Line::from(format!(
            "status {}  current_round {}/{}  sim_id {}",
            decision.simulation.status,
            decision.simulation.current_round,
            total_rounds,
            decision.simulation.simulation_id
        )),
        Line::from(""),
        Line::from(Span::styled(
            "Cast Admission",
            Style::default().add_modifier(Modifier::BOLD),
        )),
    ];
    for row in decision.simulation.selected_entities.iter().take(6) {
        lines.push(Line::from(format!(
            "{:22} {:12} score {:>4.1} thr {:>4.1}  g{} a{} s{}",
            shorten(&row.name, 22),
            shorten(&row.role, 12),
            row.score,
            row.threshold,
            row.graph_degree,
            row.anchor_overlap,
            row.summary_overlap,
        )));
        lines.push(Line::from(format!("  {}", shorten(&row.rationale, 100))));
    }
    lines.push(Line::from(""));
    lines.push(Line::from(Span::styled(
        "Signal Graphs",
        Style::default().add_modifier(Modifier::BOLD),
    )));
    for theme in decision.signals.top_themes.iter().take(4) {
        lines.push(Line::from(format!(
            "{:22} {} {}",
            shorten(&theme.theme, 22),
            meter(theme.count, top_theme_max, 16),
            theme.count
        )));
    }
    for (agent, count) in decision.simulation.top_agents.iter().take(4) {
        lines.push(Line::from(format!(
            "{:22} {} {}",
            shorten(agent, 22),
            meter(*count, top_agent_max, 16),
            count
        )));
    }
    lines.push(Line::from(""));
    lines.push(Line::from(Span::styled(
        "Drivers",
        Style::default().add_modifier(Modifier::BOLD),
    )));
    for driver in decision.forecast.drivers.iter().take(4) {
        lines.push(Line::from(format!(
            "- {} [{}] strength {:.2}",
            driver.label, driver.polarity, driver.strength
        )));
        lines.push(Line::from(format!("  {}", driver.explanation)));
    }
    lines.push(Line::from(""));
    lines.push(Line::from(Span::styled(
        "Invalidation",
        Style::default().add_modifier(Modifier::BOLD),
    )));
    for row in decision.forecast.invalidation.iter().take(3) {
        lines.push(Line::from(format!("- {}", row)));
    }
    lines.push(Line::from(""));
    lines.push(Line::from(Span::styled(
        "Resolution Notes",
        Style::default().add_modifier(Modifier::BOLD),
    )));
    lines.push(Line::from(shorten(&decision.market.resolution_notes, 900)));
    Ok(Text::from(lines))
}

fn build_evidence_text(run: &RunSummary) -> Result<Text<'static>> {
    let evidence = evidence_for_run(run)?;
    let mut lines = vec![Line::from(format!(
        "{} evidence rows",
        evidence.evidence.len()
    ))];
    for row in evidence.evidence.iter().take(24) {
        lines.push(Line::from(vec![
            Span::styled(format!("{} ", row.id), Style::default().fg(Color::Cyan)),
            Span::raw(format!(
                "{} [{} / {} / {}]",
                row.title, row.kind, row.theme, row.credibility
            )),
        ]));
        lines.push(Line::from(format!(
            "  {}  {}",
            shorten(&row.source, 30),
            shorten(&row.timestamp, 26)
        )));
        if !row.url.is_empty() {
            lines.push(Line::from(format!("  {}", shorten(&row.url, 88))));
        }
    }
    Ok(Text::from(lines))
}

fn build_alerts_text(run: &RunSummary) -> Result<Text<'static>> {
    let alerts = alerts_for_run(run)?;
    let mut lines = Vec::new();
    for row in alerts.alerts.iter() {
        lines.push(Line::from(vec![
            Span::styled(row.level.to_uppercase(), alert_style(&row.level)),
            Span::raw(format!("  {}", row.message)),
        ]));
    }
    if lines.is_empty() {
        lines.push(Line::from("No alerts."));
    }
    Ok(Text::from(lines))
}

fn build_accountability_text(topic: &TopicSummary) -> Result<Text<'static>> {
    let accountability = accountability_for_topic(topic)?;
    let market_series: Vec<f64> = accountability
        .records
        .iter()
        .map(|row| row.market_yes_probability)
        .collect();
    let model_series: Vec<f64> = accountability
        .records
        .iter()
        .map(|row| row.predicted_yes_probability)
        .collect();
    let confidence_series: Vec<f64> = accountability
        .records
        .iter()
        .map(|row| row.confidence)
        .collect();
    let mut lines = vec![
        Line::from(format!(
            "{} runs tracked for {}",
            accountability.records.len(),
            topic.topic_id
        )),
        Line::from(""),
        Line::from(Span::styled(
            "Forecast History",
            Style::default().add_modifier(Modifier::BOLD),
        )),
        Line::from(format!(
            "market     {}",
            probability_sparkline(&market_series, 44)
        )),
        Line::from(format!(
            "model      {}",
            probability_sparkline(&model_series, 44)
        )),
        Line::from(format!(
            "confidence {}",
            probability_sparkline(&confidence_series, 44)
        )),
        Line::from(""),
    ];
    for row in accountability.records.iter().rev().take(20) {
        lines.push(Line::from(vec![
            Span::styled(row.call.clone(), call_style(&row.call)),
            Span::raw(format!(
                "  {}  conf {:.0}%  mkt {}  mod {}  disloc {}",
                row.run_id,
                row.confidence * 100.0,
                yes_no_pair(row.market_yes_probability),
                yes_no_pair(row.predicted_yes_probability),
                edge_pair(row.edge),
            )),
        ]));
        lines.push(Line::from(format!(
            "  {}  {}  {}",
            shorten(&row.generated_at, 26),
            row.dominant_theme,
            row.simulation_status
        )));
    }
    Ok(Text::from(lines))
}

fn build_branch_text(
    run: &RunSummary,
    index_branches: &[BranchSummary],
    selected_branch: Option<&BranchSummary>,
) -> Result<Text<'static>> {
    let branch = if let Some(selected) = selected_branch {
        Some(selected.clone())
    } else if let Some(path_result) = branch_for_run(run) {
        Some(path_result?)
    } else {
        index_branches
            .iter()
            .find(|row| row.simulation_id == run.artifact_paths.branch.clone().unwrap_or_default())
            .cloned()
    };
    let Some(branch) = branch else {
        return Ok(Text::from(
            "No counterfactual branch metadata for the selected run.",
        ));
    };
    let lines = vec![
        Line::from(Span::styled(
            "COUNTERFACTUAL DELTA",
            Style::default().add_modifier(Modifier::BOLD),
        )),
        Line::from(format!("branch {}", branch.simulation_id)),
        Line::from(format!("base {}", branch.base_simulation_id)),
        Line::from(format!(
            "actor {} ({}) at round {}",
            branch.actor_name.unwrap_or_else(|| "n/a".to_string()),
            branch.entity_type.unwrap_or_else(|| "n/a".to_string()),
            branch
                .injection_round
                .map(|v| v.to_string())
                .unwrap_or_else(|| "n/a".to_string())
        )),
        Line::from(format!(
            "delta actions {}  diplomacy {}  conflict {}  interpretation {}",
            branch
                .action_delta
                .map(|v| v.to_string())
                .unwrap_or_else(|| "n/a".to_string()),
            branch
                .diplomacy_delta
                .map(|v| v.to_string())
                .unwrap_or_else(|| "n/a".to_string()),
            branch
                .conflict_delta
                .map(|v| v.to_string())
                .unwrap_or_else(|| "n/a".to_string()),
            branch.interpretation.unwrap_or_else(|| "n/a".to_string())
        )),
        Line::from(""),
        Line::from(shorten(&branch.opening_statement.unwrap_or_default(), 800)),
    ];
    Ok(Text::from(lines))
}

fn alert_style(level: &str) -> Style {
    match level {
        "critical" => Style::default().fg(Color::Red).add_modifier(Modifier::BOLD),
        "warning" => Style::default()
            .fg(Color::Yellow)
            .add_modifier(Modifier::BOLD),
        _ => Style::default()
            .fg(Color::Blue)
            .add_modifier(Modifier::BOLD),
    }
}

fn render_splash(frame: &mut Frame, stage: &str, step: usize, topic_id: Option<&str>) {
    let area = frame.area();
    let popup = centered_rect(84, 58, area);
    let progress_width = 42;
    let filled = ((step + 1) * progress_width / 14).min(progress_width);
    let bar = format!(
        "[{}{}]",
        "#".repeat(filled),
        ".".repeat(progress_width.saturating_sub(filled))
    );
    let topic_hint = topic_id.unwrap_or("all-topics");
    let art = [
        " ____  ____  _____ ____ ___ _   _ _____ ____  __  __ _____ ____ ",
        "|  _ \\|  _ \\| ____/ ___|_ _| | | | ____|  _ \\|  \\/  | ____/ ___|",
        "| |_) | |_) |  _|| |    | || |_| |  _| | |_) | |\\/| |  _| \\___ \\",
        "|  __/|  _ <| |__| |___ | ||  _  | |___|  _ <| |  | | |___ ___) |",
        "|_|   |_| \\_\\_____\\____|___|_| |_|_____|_| \\_\\_|  |_|_____|____/ ",
    ];
    let lines = Text::from(vec![
        Line::from(""),
        Line::from(art[0]),
        Line::from(art[1]),
        Line::from(art[2]),
        Line::from(art[3]),
        Line::from(art[4]),
        Line::from(""),
        Line::from("        ingest -> score -> branch -> compare -> decide       "),
        Line::from("        evidence -> ledger -> control-room -> operator       "),
        Line::from(""),
        Line::from(format!("        target  :: {}", topic_hint)),
        Line::from(format!("        phase   :: {}", stage)),
        Line::from(""),
        Line::from(format!("        boot    :: {}", bar)),
        Line::from(format!("        sweep   :: {}", pulse_bar(step as u64, 28))),
    ]);
    let paragraph = Paragraph::new(lines)
        .block(
            Block::default()
                .borders(Borders::ALL)
                .title(":: PREDIHERMES BOOTSTRAP ::"),
        )
        .wrap(Wrap { trim: false });
    frame.render_widget(paragraph, popup);
}

fn centered_rect(percent_x: u16, percent_y: u16, area: Rect) -> Rect {
    let vertical = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Percentage((100 - percent_y) / 2),
            Constraint::Percentage(percent_y),
            Constraint::Percentage((100 - percent_y) / 2),
        ])
        .split(area);
    Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage((100 - percent_x) / 2),
            Constraint::Percentage(percent_x),
            Constraint::Percentage((100 - percent_x) / 2),
        ])
        .split(vertical[1])[1]
}

fn boot_sequence(terminal: &mut DefaultTerminal, topic_id: Option<&str>) -> Result<()> {
    let stages = [
        "bind local ledgers",
        "index topic lattice",
        "hydrate evidence bus",
        "prime branch matrix",
        "arm control room",
        "open operator deck",
    ];
    for step in 0..14 {
        let stage = stages[(step / 2).min(stages.len() - 1)];
        terminal.draw(|frame| render_splash(frame, stage, step, topic_id))?;
        sleep(Duration::from_millis(85));
    }
    Ok(())
}

fn render_footer(frame: &mut Frame, area: Rect, app: &App) {
    let lines = vec![
        Line::from(format!(
            "[{}] focus {}  signal {}",
            spinner(app.tick + 4),
            focus_label(app.focus),
            pulse_bar(app.tick + 5, 14)
        )),
        Line::from("1 topics  2 runs  3 branches  4 tabs  5 detail  Tab cycle  j/k move  h/l tabs"),
        Line::from(
            "r reload  ? help  Enter open branch detail  c show branch-create command  q quit",
        ),
        Line::from(app.footer_message.clone()),
    ];
    let paragraph = Paragraph::new(lines).block(
        Block::default()
            .borders(Borders::ALL)
            .title(":: CONTROL ROOM / SIGNAL ::"),
    );
    frame.render_widget(paragraph, area);
}

fn render_help_overlay(frame: &mut Frame) {
    let popup = centered_rect(74, 52, frame.area());
    let lines = Text::from(vec![
        Line::from(""),
        Line::from(Span::styled(
            "PREDIHERMES NAVIGATION",
            Style::default()
                .fg(Color::Yellow)
                .add_modifier(Modifier::BOLD),
        )),
        Line::from(""),
        Line::from("Tab        cycle focus across panes"),
        Line::from("1/2/3/4/5 focus Topics / Runs / Branches / Tabs / Detail"),
        Line::from("j/k        move within focused pane"),
        Line::from("h/l        change detail tab"),
        Line::from("u/d        page detail pane"),
        Line::from("Enter      open selected branch in detail tab"),
        Line::from("c          generate branch creation command from selected/base sim"),
        Line::from("r          recompile + reload the live ledgers"),
        Line::from("?          toggle this help"),
        Line::from("q          quit"),
        Line::from(""),
        Line::from("Fresh runs auto-sync every few seconds while the TUI is open."),
        Line::from("Branch creation itself stays explicit in the CLI/skill path."),
        Line::from("Use `predihermes create-branch ...` or ask Hermes to do it."),
    ]);
    let paragraph = Paragraph::new(lines)
        .block(
            Block::default()
                .borders(Borders::ALL)
                .title(":: HELP ::")
                .border_style(Style::default().fg(Color::Yellow)),
        )
        .wrap(Wrap { trim: false });
    frame.render_widget(paragraph, popup);
}

fn shorten(value: &str, limit: usize) -> String {
    if value.chars().count() <= limit {
        return value.to_string();
    }
    value
        .chars()
        .take(limit.saturating_sub(3))
        .collect::<String>()
        + "..."
}

fn handle_key(app: &mut App, code: KeyCode) -> Result<bool> {
    match code {
        KeyCode::Char('q') => return Ok(true),
        KeyCode::Char('r') => {
            let changed = app.refresh_from_source()?;
            app.footer_message = if changed {
                "live runs refreshed from source".to_string()
            } else {
                "no new runs since last refresh".to_string()
            };
            return Ok(false);
        }
        KeyCode::Char('?') => {
            app.show_help = !app.show_help;
            return Ok(false);
        }
        KeyCode::Tab => {
            app.cycle_focus();
            app.detail_scroll = 0;
        }
        KeyCode::Char('1') => app.focus = Focus::Topics,
        KeyCode::Char('2') => app.focus = Focus::Runs,
        KeyCode::Char('3') => app.focus = Focus::Branches,
        KeyCode::Char('4') => app.focus = Focus::Tabs,
        KeyCode::Char('5') => app.focus = Focus::Detail,
        KeyCode::Char('h') | KeyCode::Left => {
            if app.focus == Focus::Tabs && app.detail_tab > 0 {
                app.detail_tab -= 1;
                app.detail_scroll = 0;
            }
        }
        KeyCode::Char('l') | KeyCode::Right => {
            if app.focus == Focus::Tabs && app.detail_tab + 1 < DetailTab::all().len() {
                app.detail_tab += 1;
                app.detail_scroll = 0;
            }
        }
        KeyCode::Char('j') | KeyCode::Down => match app.focus {
            Focus::Topics => {
                if app.topic_idx + 1 < app.index.topics.len() {
                    app.topic_idx += 1;
                    app.select_latest_run();
                }
            }
            Focus::Runs => {
                let runs = app.topic_runs();
                if app.run_idx + 1 < runs.len() {
                    app.run_idx += 1;
                }
            }
            Focus::Branches => {
                let branches = app.topic_branches();
                if app.branch_idx + 1 < branches.len() {
                    app.branch_idx += 1;
                }
            }
            Focus::Tabs => {
                if app.detail_tab + 1 < DetailTab::all().len() {
                    app.detail_tab += 1;
                    app.detail_scroll = 0;
                }
            }
            Focus::Detail => {
                app.detail_scroll = app.detail_scroll.saturating_add(1);
            }
        },
        KeyCode::Char('k') | KeyCode::Up => match app.focus {
            Focus::Topics => {
                if app.topic_idx > 0 {
                    app.topic_idx -= 1;
                    app.select_latest_run();
                }
            }
            Focus::Runs => {
                if app.run_idx > 0 {
                    app.run_idx -= 1;
                }
            }
            Focus::Branches => {
                if app.branch_idx > 0 {
                    app.branch_idx -= 1;
                }
            }
            Focus::Tabs => {
                if app.detail_tab > 0 {
                    app.detail_tab -= 1;
                    app.detail_scroll = 0;
                }
            }
            Focus::Detail => {
                app.detail_scroll = app.detail_scroll.saturating_sub(1);
            }
        },
        KeyCode::Char('g') => match app.focus {
            Focus::Topics => {
                app.topic_idx = 0;
                app.select_latest_run();
            }
            Focus::Runs => app.run_idx = 0,
            Focus::Branches => app.branch_idx = 0,
            _ => {}
        },
        KeyCode::Char('G') => match app.focus {
            Focus::Topics => {
                app.topic_idx = app.index.topics.len().saturating_sub(1);
                app.select_latest_run();
            }
            Focus::Runs => {
                let len = app.topic_runs().len();
                app.run_idx = len.saturating_sub(1);
            }
            Focus::Branches => {
                let len = app.topic_branches().len();
                app.branch_idx = len.saturating_sub(1);
            }
            _ => {}
        },
        KeyCode::Char('u') => {
            if app.focus == Focus::Detail {
                app.detail_scroll = app.detail_scroll.saturating_sub(8);
            }
        }
        KeyCode::Char('d') => {
            if app.focus == Focus::Detail {
                app.detail_scroll = app.detail_scroll.saturating_add(8);
            }
        }
        KeyCode::Enter => {
            if app.focus == Focus::Branches && app.current_branch().is_some() {
                app.focus = Focus::Detail;
                app.detail_tab = 4;
                app.detail_scroll = 0;
                app.footer_message = "branch detail opened".to_string();
            }
        }
        KeyCode::Char('c') => {
            if let Some(run) = app.current_run() {
                if let Some(simulation_id) = simulation_id_for_run(run) {
                    app.footer_message = format!(
                        "branch seed :: predihermes create-branch --base-simulation-id {} --actor-name \"New actor\" --entity-type Organization --injection-round 8 --opening-statement \"...\"",
                        simulation_id
                    );
                } else {
                    app.footer_message =
                        "selected run has no simulation id; pick a completed sim-backed run first"
                            .to_string();
                }
            }
        }
        _ => {}
    }
    app.align_run_to_topic();
    app.align_branch_to_topic();
    Ok(false)
}

fn run_app(mut terminal: DefaultTerminal, mut app: App) -> Result<()> {
    loop {
        terminal.draw(|frame| render(frame, &app))?;
        if event::poll(Duration::from_millis(250))? {
            if let Event::Key(key) = event::read()? {
                if key.kind == KeyEventKind::Press && handle_key(&mut app, key.code)? {
                    return Ok(());
                }
            }
        }
        app.tick = app.tick.wrapping_add(1);
        if app.last_refresh_at.elapsed() >= app.auto_refresh_interval {
            if let Ok(changed) = app.refresh_from_source() {
                if changed {
                    app.footer_message = "new run data synced into control room".to_string();
                }
            }
        }
    }
}

fn main() -> Result<()> {
    let cli = resolve_cli_args();
    let index = load_index(&cli.data_root).with_context(|| {
        format!(
            "compiled index missing. Run `python3 tmp_geopolitical_market_pipeline.py compile-artifacts --mirofish-root {}` first",
            env::current_dir().unwrap_or_else(|_| PathBuf::from(".")).display()
        )
    })?;

    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let mut terminal = ratatui::init();
    boot_sequence(&mut terminal, cli.topic_id.as_deref())?;
    let result = run_app(
        terminal,
        App::new(
            cli.data_root,
            index,
            cli.topic_id.as_deref(),
            cli.compile_python,
            cli.compile_script,
            cli.compile_mirofish_root,
            Duration::from_secs(cli.auto_refresh_seconds),
        ),
    );
    disable_raw_mode()?;
    execute!(io::stdout(), LeaveAlternateScreen)?;
    ratatui::restore();
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn call_style_is_stable() {
        assert_eq!(pct(0.0245), "2.5%");
        assert_eq!(shorten("abcdef", 4), "a...");
    }
}
