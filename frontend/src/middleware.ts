// Private site: when CABINA_PASSWORD is set (on the hosting), every page asks for it
// (browser login box, any user name). Without it (local development) the site is open.
import { NextResponse, type NextRequest } from "next/server";

export function middleware(req: NextRequest) {
  const password = process.env.CABINA_PASSWORD;
  if (!password) return NextResponse.next();
  const auth = req.headers.get("authorization") ?? "";
  if (auth.startsWith("Basic ")) {
    try {
      const decoded = atob(auth.slice(6));
      if (decoded.slice(decoded.indexOf(":") + 1) === password) return NextResponse.next();
    } catch { /* malformed header: ask again */ }
  }
  return new NextResponse("Accesso riservato", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="RoyauMoney", charset="UTF-8"' },
  });
}

export const config = { matcher: "/((?!_next/static|_next/image|favicon.ico).*)" };
