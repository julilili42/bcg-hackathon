import { useEvents } from "./api";

export default function Dashboard() {
  const { events, waterpoints } = useEvents(5000);
  return (
    <main className="dash">
      <h2>Water points</h2>
      <table>
        <thead><tr><th>Name</th><th>Village</th><th>Status</th><th>Updated (UTC)</th></tr></thead>
        <tbody>{waterpoints.map((w) => (
          <tr key={w.id}><td>{w.name}</td><td>{w.village}</td><td className={`status ${w.status}`}>{w.status}</td><td>{w.updated}</td></tr>
        ))}</tbody>
      </table>
      <h2>Calls and messages <small>({events.length})</small> <a href="/api/map">map</a></h2>
      <table>
        <thead><tr><th>Time (UTC)</th><th>Channel</th><th>From</th><th>Lang</th><th>Said</th><th>Answered</th></tr></thead>
        <tbody>{events.map((e) => (
          <tr key={e.id}><td>{e.ts}</td><td>{e.channel}</td><td>{e.sender}</td><td>{e.lang}</td><td>{e.body}</td><td>{e.reply}</td></tr>
        ))}</tbody>
      </table>
    </main>
  );
}
