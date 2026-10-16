import { createRoot } from "react-dom/client";
import Phone from "./Phone";
import Dashboard from "./Dashboard";
import MapPage from "./Map";
import "./app.css";

// One build, three pages: /api/phone, /api/dashboard, /api/map.
const pages = { phone: Phone, dashboard: Dashboard, map: MapPage };
const name = location.pathname.replace(/\/$/, "").split("/").pop() as keyof typeof pages;
const Page = pages[name] ?? Dashboard;
createRoot(document.getElementById("root")!).render(<Page />);
