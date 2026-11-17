// The backend's answers (src/wikicross/app.py) and the API both pages provide to their components.
import type { InjectionKey } from "vue";

export type Kind = "factual" | "bias" | "framing";  // app.KINDS

/** A finding's sentence in one edition, with its passage (page_id, seq) and its place in it (n). */
export interface Member {
  lang: string;
  title: string;
  heading: string;
  text: string;
  page_id: number;
  seq: number;
  n: number;
  sentence: string;
}

/** compare.differences(): editions placed apart on a framing axis. */
export interface Finding {
  kind: "framing";
  axis: string;
  ends: [string, string];
  lang: string;  // the edition furthest from the others' average
  deviation: number;
  deviations: Record<string, number>;
  outlier: boolean;
  distance: number;
  members: Member[];
}

export interface Article { lang: string; title: string; url: string }

/** A diff's steps and how far it got: each visited step with the second it began. */
export interface Progress {
  steps: { key: string; label: string }[];
  visited: [string, number][];
  detail: string;
  seconds: number;
}

export interface Diff {
  wikidata_id: string;
  articles: Article[];
  languages: string[];
  differences: Finding[];
  total: number;
  progress: Progress;
}

export interface TitleSuggestion {
  wikidata_id: string | null;
  lang: string;
  title: string;
  description: string | null;
  thumbnail: string | null;
}

export interface Explanation {
  discrepancy: boolean;
  kind: Kind | null;
  title: string;
  description: string;
  quotes: Record<string, { english: string; heading: string; phrases: string[] }>;
}

export interface ContextSentence { seq: number; n: number; heading: string; text: string }

export interface Limits { api: number; llm: number }

/** Quotes in English, by language: the AI's or the translator's. */
export type English = Record<string, { quote: string; heading: string }>;

/** A load's timings (performance.now()) and its AI step, for LoadingSteps. */
export interface Times { start: number; result: number | null; aiDone: number | null }
/** Which editions are compared (LanguageFilter): langs null is all. */
export interface Filters { langs: string[] | null; dialects: boolean }

export interface AiStep { total: number; settled: number; failed: number }

export type Params = Record<string, string | number | boolean>;
/** A failed request: the backend's message, and its HTTP status (0: no answer at all). */
export type ApiError = Error & { status: number };
export interface Api {
  get<T>(path: string, params?: Params): Promise<T>;
  post<T>(path: string, body: unknown): Promise<T>;
}
export const API: InjectionKey<Api> = Symbol("api");

export const errorText = (err: unknown) => (err instanceof Error ? err.message : String(err));
export const statusOf = (err: unknown) => (err as Partial<ApiError>).status ?? 0;
