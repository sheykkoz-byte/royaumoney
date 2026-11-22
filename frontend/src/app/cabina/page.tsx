import { redirect } from "next/navigation";

// The cockpit is now the home page; old bookmarks to /cabina still work.
export default function OldCabina() {
  redirect("/");
}
