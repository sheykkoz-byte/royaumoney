import "./fake-ws"; // must run before the page creates its socket
import "./mic"; // platform dictation in place of the blocked microphone
import { createRoot } from "react-dom/client";
import Jarvis from "@/app/page";

createRoot(document.getElementById("root")!).render(<Jarvis />);
