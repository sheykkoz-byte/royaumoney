import "./fake-ws"; // must run before the page creates its socket
import "./mic"; // platform dictation in place of the blocked microphone
import "./tts-voice"; // Claude's voice in place of the browser's, for Claude-brain answers
import { createRoot } from "react-dom/client";
import Jarvis from "@/app/page";

createRoot(document.getElementById("root")!).render(<Jarvis />);
