// Market catalogue of the cockpit's watchlist, in TradingView symbol format (EXCHANGE:TICKER).
// Any other TradingView symbol can be added from the search box.

export type Sym = { s: string; n: string }; // symbol, Italian name
export type Category = { id: string; name: string; items: Sym[] };

export const CATEGORIES: Category[] = [
  { id: "fx-major", name: "Forex · principali", items: [
    { s: "FX:EURUSD", n: "Euro / Dollaro" }, { s: "FX:GBPUSD", n: "Sterlina / Dollaro" },
    { s: "FX:USDJPY", n: "Dollaro / Yen" }, { s: "FX:USDCHF", n: "Dollaro / Franco svizzero" },
    { s: "FX:AUDUSD", n: "Dollaro australiano / Dollaro" }, { s: "FX:USDCAD", n: "Dollaro / Dollaro canadese" },
    { s: "FX:NZDUSD", n: "Dollaro neozelandese / Dollaro" },
  ] },
  { id: "fx-cross", name: "Forex · incroci", items: [
    { s: "FX:EURGBP", n: "Euro / Sterlina" }, { s: "FX:EURJPY", n: "Euro / Yen" },
    { s: "FX:GBPJPY", n: "Sterlina / Yen" }, { s: "FX:EURCHF", n: "Euro / Franco svizzero" },
    { s: "FX:AUDJPY", n: "Dollaro australiano / Yen" }, { s: "FX:EURAUD", n: "Euro / Dollaro australiano" },
    { s: "FX:GBPCHF", n: "Sterlina / Franco svizzero" }, { s: "FX:CADJPY", n: "Dollaro canadese / Yen" },
  ] },
  { id: "fx-exotic", name: "Forex · esotiche", items: [
    { s: "FX_IDC:USDMAD", n: "Dollaro / Dirham marocchino" }, { s: "FX_IDC:EURMAD", n: "Euro / Dirham marocchino" },
    { s: "FX:USDTRY", n: "Dollaro / Lira turca" }, { s: "FX:USDZAR", n: "Dollaro / Rand" },
    { s: "FX:USDMXN", n: "Dollaro / Peso messicano" }, { s: "FX:USDCNH", n: "Dollaro / Yuan offshore" },
  ] },
  { id: "metals", name: "Metalli", items: [
    { s: "OANDA:XAUUSD", n: "Oro spot" }, { s: "OANDA:XAGUSD", n: "Argento spot" },
    { s: "OANDA:XPTUSD", n: "Platino" }, { s: "OANDA:XPDUSD", n: "Palladio" },
    { s: "OANDA:XCUUSD", n: "Rame" },
  ] },
  { id: "energy-agri", name: "Energia e agricole", items: [
    { s: "TVC:USOIL", n: "Petrolio WTI" }, { s: "TVC:UKOIL", n: "Petrolio Brent" },
    { s: "CAPITALCOM:NATURALGAS", n: "Gas naturale" }, { s: "CAPITALCOM:WHEAT", n: "Grano" },
    { s: "CAPITALCOM:CORN", n: "Mais" }, { s: "CAPITALCOM:SOYBEAN", n: "Soia" },
    { s: "CAPITALCOM:COFFEEARABICA", n: "Caffè" }, { s: "CAPITALCOM:COCOA", n: "Cacao" },
    { s: "CAPITALCOM:SUGAR", n: "Zucchero" },
  ] },
  { id: "indices", name: "Indici", items: [
    { s: "FOREXCOM:SPXUSD", n: "S&P 500" }, { s: "FOREXCOM:NSXUSD", n: "Nasdaq 100" },
    { s: "FOREXCOM:DJI", n: "Dow Jones" }, { s: "FOREXCOM:US2000", n: "Russell 2000" },
    { s: "XETR:DAX", n: "DAX" }, { s: "INDEX:FTSEMIB", n: "FTSE MIB" },
    { s: "CAPITALCOM:EU50", n: "Euro Stoxx 50" }, { s: "CAPITALCOM:UK100", n: "FTSE 100" },
    { s: "EURONEXT:PX1", n: "CAC 40" }, { s: "CAPITALCOM:J225", n: "Nikkei 225" },
    { s: "CAPITALCOM:HK50", n: "Hang Seng" }, { s: "CSEMA:MASI", n: "MASI (Casablanca)" },
  ] },
  { id: "dollar-vol", name: "Dollaro e volatilità", items: [
    { s: "CAPITALCOM:DXY", n: "Indice del dollaro (DXY, CFD)" },
    { s: "FRED:VIXCLS", n: "VIX ufficiale (chiusura giornaliera)" },
    { s: "CAPITALCOM:VIX", n: "VIX CFD sul future (tempo reale)" },
  ] },
  // Yields: TradingView's own (TVC) are not allowed in embedded charts; FRED's official
  // series are (daily close for the US, monthly for Italy, UK and Japan).
  { id: "bonds", name: "Obbligazioni e tassi", items: [
    { s: "FRED:DGS2", n: "Treasury 2 anni" }, { s: "FRED:DGS5", n: "Treasury 5 anni" },
    { s: "FRED:DGS10", n: "Treasury 10 anni" }, { s: "FRED:DGS30", n: "Treasury 30 anni" },
    { s: "FRED:T10Y2Y", n: "Curva 10 − 2 anni" }, { s: "FRED:T10Y3M", n: "Curva 10 anni − 3 mesi" },
    { s: "FRED:DFII10", n: "Rendimento reale 10 anni" }, { s: "FRED:T5YIFR", n: "Inflazione attesa 5 anni fra 5" },
    { s: "FRED:DFF", n: "Fed funds" }, { s: "TRADEWEB:DE10Y", n: "Bund 10 anni" },
    { s: "FRED:IRLTLT01ITM156N", n: "BTP 10 anni (mensile)" },
    { s: "FRED:IRLTLT01ITM156N-FRED:IRLTLT01DEM156N", n: "Spread BTP − Bund (mensile)" },
    { s: "FRED:IRLTLT01GBM156N", n: "Gilt 10 anni (mensile)" },
    { s: "FRED:IRLTLT01JPM156N", n: "JGB 10 anni (mensile)" },
  ] },
  { id: "crypto", name: "Crypto", items: [
    { s: "BITSTAMP:BTCUSD", n: "Bitcoin" }, { s: "BITSTAMP:ETHUSD", n: "Ethereum" },
    { s: "BINANCE:SOLUSDT", n: "Solana" }, { s: "BINANCE:XRPUSDT", n: "XRP" },
    { s: "BINANCE:BNBUSDT", n: "BNB" }, { s: "CRYPTOCAP:BTC.D", n: "Dominanza Bitcoin" },
  ] },
  { id: "stocks-us", name: "Azioni USA", items: [
    { s: "NASDAQ:AAPL", n: "Apple" }, { s: "NASDAQ:MSFT", n: "Microsoft" },
    { s: "NASDAQ:NVDA", n: "Nvidia" }, { s: "NASDAQ:AMZN", n: "Amazon" },
    { s: "NASDAQ:GOOGL", n: "Alphabet" }, { s: "NASDAQ:META", n: "Meta" },
    { s: "NASDAQ:TSLA", n: "Tesla" }, { s: "NYSE:JPM", n: "JPMorgan" },
  ] },
  { id: "stocks-it", name: "Azioni Italia", items: [
    { s: "MIL:ENI", n: "Eni" }, { s: "MIL:ISP", n: "Intesa Sanpaolo" },
    { s: "MIL:UCG", n: "UniCredit" }, { s: "MIL:ENEL", n: "Enel" }, { s: "MIL:STLAM", n: "Stellantis" },
  ] },
  { id: "sectors", name: "Settori USA (ETF)", items: [
    { s: "AMEX:XLK", n: "Tecnologia" }, { s: "AMEX:XLF", n: "Finanziari" },
    { s: "AMEX:XLE", n: "Energia" }, { s: "AMEX:XLI", n: "Industriali" },
    { s: "AMEX:XLY", n: "Consumi discrezionali" }, { s: "AMEX:XLP", n: "Beni di prima necessità" },
    { s: "AMEX:XLU", n: "Utility" }, { s: "AMEX:XLV", n: "Sanità" },
  ] },
];

export const DEFAULT_FAVORITES = [
  "OANDA:XAUUSD", "FX:EURUSD", "FX:USDJPY", "FOREXCOM:SPXUSD", "FOREXCOM:NSXUSD",
  "CAPITALCOM:DXY", "CAPITALCOM:VIX", "TVC:USOIL", "BITSTAMP:BTCUSD",
];

export const DEFAULT_MINI = ["CAPITALCOM:DXY", "FRED:DGS10", "FRED:VIXCLS", "FRED:T10Y2Y"];

const BY_SYMBOL = new Map(CATEGORIES.flatMap((c) => c.items.map((i) => [i.s, i.n] as const)));

/** Italian name of a symbol, or its ticker when it is not in the catalogue. */
export function nameOf(symbol: string): string {
  return BY_SYMBOL.get(symbol) ?? symbol.split(":").pop() ?? symbol;
}

/** Search the catalogue by ticker or name (accents ignored). */
export function search(q: string): Sym[] {
  const f = (x: string) => x.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const k = f(q.trim());
  if (!k) return [];
  return CATEGORIES.flatMap((c) => c.items).filter((i) => f(i.s).includes(k) || f(i.n).includes(k));
}
