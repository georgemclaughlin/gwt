export interface GwtClientOptions {
  file: string;
  command?: string;
  commandArgs?: string[];
  cwd?: string;
  env?: Record<string, string | undefined>;
}

export interface GwtRunJsonOptions {
  entry: string;
  cwd?: string;
  env?: Record<string, string | undefined>;
}

export interface GwtRunRequestOptions {
  cwd?: string;
  env?: Record<string, string | undefined>;
}

export interface GwtCheckOptions {
  cwd?: string;
  env?: Record<string, string | undefined>;
}

export type GwtPayload = Record<string, unknown>;

export interface GwtScenarioPayload<
  TResult extends object = GwtPayload,
  TState extends object = GwtPayload,
> {
  name: string;
  state: TState;
  result: TResult;
  output: string[];
}

export interface GwtExecutionEnvelope<
  TResult extends object = GwtPayload,
  TState extends object = GwtPayload,
> {
  ok: true;
  file: string | null;
  request_file: string | null;
  scenario_count: number;
  scenarios: GwtScenarioPayload<TResult, TState>[];
  state: TState | null;
  result: TResult | null;
  output: string[] | null;
}

export interface GwtSingleExecutionEnvelope<
  TResult extends object = GwtPayload,
  TState extends object = GwtPayload,
> extends GwtExecutionEnvelope<TResult, TState> {
  scenario_count: 1;
  state: TState;
  result: TResult;
  output: string[];
}

export interface GwtCheckPayload extends GwtPayload {
  ok: boolean;
  file: string;
  program: string | null;
  inputs: number;
  outputs: number;
  dtos: number;
  behaviors: number;
  scenarios: number;
  diagnostics: unknown[];
  symbols: unknown[];
}

export class GwtClientError extends Error {
  exitCode: number | null;
  stdout: string;
  stderr: string;
}

export class GwtClient {
  constructor(options: string | GwtClientOptions);

  file: string;
  command: string;
  commandArgs: string[];
  cwd?: string;
  env?: Record<string, string | undefined>;

  check(options?: GwtCheckOptions): Promise<GwtCheckPayload>;
  runJson<
    TInput extends object = GwtPayload,
    TResult extends object = GwtPayload,
    TState extends object = GwtPayload,
  >(
    input: TInput,
    options: GwtRunJsonOptions,
  ): Promise<GwtSingleExecutionEnvelope<TResult, TState>>;
  runRequest<TResult extends object = GwtPayload, TState extends object = GwtPayload>(
    requestFile: string,
    options?: GwtRunRequestOptions,
  ): Promise<GwtExecutionEnvelope<TResult, TState>>;
}

export function checkFile(
  file: string,
  options?: Omit<GwtClientOptions, "file"> & GwtCheckOptions,
): Promise<GwtCheckPayload>;

export function runFile<
  TInput extends object = GwtPayload,
  TResult extends object = GwtPayload,
  TState extends object = GwtPayload,
>(
  file: string,
  options: Omit<GwtClientOptions, "file"> & {
    input: TInput;
    entry: string;
    requestFile?: never;
  },
): Promise<GwtSingleExecutionEnvelope<TResult, TState>>;

export function runFile<TResult extends object = GwtPayload, TState extends object = GwtPayload>(
  file: string,
  options: Omit<GwtClientOptions, "file"> & {
    requestFile: string;
    input?: never;
    entry?: never;
  },
): Promise<GwtExecutionEnvelope<TResult, TState>>;
