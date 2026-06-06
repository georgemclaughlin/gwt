export interface GwtImportPolicyOptions {
  importRoots?: string[];
  allowAbsoluteImports?: boolean;
}

export interface GwtClientOptions {
  file: string;
  command?: string;
  commandArgs?: string[];
  cwd?: string;
  env?: Record<string, string | undefined>;
  importRoots?: string[];
  allowAbsoluteImports?: boolean;
}

export interface GwtRunJsonOptions<TRequest extends string = string> extends GwtImportPolicyOptions {
  request: TRequest;
  cwd?: string;
  env?: Record<string, string | undefined>;
}

export interface GwtRunRequestOptions extends GwtImportPolicyOptions {
  cwd?: string;
  env?: Record<string, string | undefined>;
}

export interface GwtTestOptions extends GwtImportPolicyOptions {
  cwd?: string;
  env?: Record<string, string | undefined>;
}

export interface GwtCheckOptions extends GwtImportPolicyOptions {
  cwd?: string;
  env?: Record<string, string | undefined>;
}

export interface GwtSpecOptions<TRequest extends string = string> extends GwtClientOptions {
  request?: TRequest;
  checkBeforeRun?: boolean;
}

export interface GwtSpecRuntimeOptions<TRequest extends string = string> {
  request?: TRequest;
  checkBeforeRun?: boolean;
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
  schemaVersion: number;
  ok: boolean;
  file: string;
  program: string | null;
  requests: number;
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
  importRoots: string[];
  allowAbsoluteImports: boolean;

  check(options?: GwtCheckOptions): Promise<GwtCheckPayload>;
  runJson<
    TInput extends object = GwtPayload,
    TResult extends object = GwtPayload,
    TState extends object = GwtPayload,
    TRequest extends string = string,
  >(
    input: TInput,
    options: GwtRunJsonOptions<TRequest>,
  ): Promise<GwtSingleExecutionEnvelope<TResult, TState>>;
  runRequest<TResult extends object = GwtPayload, TState extends object = GwtPayload>(
    requestFile: string,
    options?: GwtRunRequestOptions,
  ): Promise<GwtExecutionEnvelope<TResult, TState>>;
  test<TResult extends object = GwtPayload, TState extends object = GwtPayload>(
    options?: GwtTestOptions,
  ): Promise<GwtExecutionEnvelope<TResult, TState>>;
}

export class GwtSpec<
  TInput extends object = GwtPayload,
  TResult extends object = GwtPayload,
  TState extends object = GwtPayload,
  TRequest extends string = string,
> {
  constructor(
    options: string | GwtClient | GwtSpecOptions<TRequest>,
    specOptions?: GwtSpecRuntimeOptions<TRequest>,
  );

  client: GwtClient;
  request?: TRequest;
  checkBeforeRun: boolean;

  checkOnce(options?: GwtCheckOptions): Promise<GwtCheckPayload>;
  resetCheck(): void;
  runJson(
    input: TInput,
    options?: Partial<GwtRunJsonOptions<TRequest>>,
  ): Promise<GwtSingleExecutionEnvelope<TResult, TState>>;
  runRequest(
    requestFile: string,
    options?: GwtRunRequestOptions,
  ): Promise<GwtExecutionEnvelope<TResult, TState>>;
  test(options?: GwtTestOptions): Promise<GwtExecutionEnvelope<TResult, TState>>;
}

export function createGwtSpec<
  TInput extends object = GwtPayload,
  TResult extends object = GwtPayload,
  TState extends object = GwtPayload,
  TRequest extends string = string,
>(
  options: string | GwtClient | GwtSpecOptions<TRequest>,
  specOptions?: GwtSpecRuntimeOptions<TRequest>,
): GwtSpec<TInput, TResult, TState, TRequest>;

export function checkFile(
  file: string,
  options?: Omit<GwtClientOptions, "file"> & GwtCheckOptions,
): Promise<GwtCheckPayload>;

export function runFile<
  TInput extends object = GwtPayload,
  TResult extends object = GwtPayload,
  TState extends object = GwtPayload,
  TRequest extends string = string,
>(
  file: string,
  options: Omit<GwtClientOptions, "file"> & {
    input: TInput;
    request: TRequest;
    requestFile?: never;
  },
): Promise<GwtSingleExecutionEnvelope<TResult, TState>>;

export function runFile<TResult extends object = GwtPayload, TState extends object = GwtPayload>(
  file: string,
  options: Omit<GwtClientOptions, "file"> & {
    requestFile: string;
    input?: never;
    request?: never;
  },
): Promise<GwtExecutionEnvelope<TResult, TState>>;
