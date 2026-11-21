import "./fake-ws"; // must run before the page creates its socket
import { createRoot } from "react-dom/client";
import Jarvis from "@/app/page";

createRoot(document.getElementById("root")!).render(<Jarvis />);
