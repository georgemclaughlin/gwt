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

export interface GwtInspectOptions extends GwtImportPolicyOptions {
  cwd?: string;
  env?: Record<string, string | undefined>;
}

export interface GwtValidateOptions extends GwtImportPolicyOptions {
  cwd?: string;
  env?: Record<string, string | undefined>;
  checkFormat?: boolean;
  runTests?: boolean;
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

export interface GwtDiagnosticPayload extends GwtPayload {
  path?: string;
  range?: unknown;
  severity?: "error" | "warning" | string;
  source?: string;
  code?: string;
  subcode?: string;
  category?: string | null;
  message?: string;
  expected?: string;
  actual?: string;
  help?: string | null;
}

export interface GwtProgramIdentityModulePayload {
  specifier: string;
  digest: string;
  imports: string[];
}

export interface GwtProgramIdentityPayload {
  algorithm: "gwt-program-closure-sha256-v1";
  entry: string;
  digest: string;
  modules: GwtProgramIdentityModulePayload[];
}

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
  records: number;
  behaviors: number;
  scenarios: number;
  diagnostics: GwtDiagnosticPayload[];
  symbols: unknown[];
}

export interface GwtInspectPayload extends GwtPayload {
  schemaVersion: number;
  ok: boolean;
  file: string;
  program: string | null;
  programHash: string;
  programHashScope?: "entry-source";
  programIdentity?: GwtProgramIdentityPayload | null;
  imports: unknown[];
  diagnostics: GwtDiagnosticPayload[];
  records: unknown[];
  oneOfRecords: unknown[];
  requests: unknown[];
  behaviors: unknown[];
  scenarios: unknown[];
  counts: {
    records: number;
    oneOfRecords: number;
    requests: number;
    behaviors: number;
    scenarios: number;
  };
}

export interface GwtValidatePayload extends GwtPayload {
  schemaVersion: number;
  ok: boolean;
  file: string;
  program: string | null;
  phases: Record<string, Record<string, unknown>>;
  diagnostics: GwtDiagnosticPayload[];
}

export type GwtRequestNameFor<TRequests, TOutputs> = Extract<keyof TRequests & keyof TOutputs, string>;
export type GwtRequestFor<TRequests, TRequest extends keyof TRequests> =
  TRequests[TRequest] extends object ? TRequests[TRequest] : never;
export type GwtOutputFor<TOutputs, TRequest extends keyof TOutputs> =
  TOutputs[TRequest] extends object ? TOutputs[TRequest] : never;
export type GwtIsUnion<T, U = T> = T extends unknown ? ([U] extends [T] ? false : true) : false;
export type GwtDefaultRequestFor<TRequests, TRequest extends keyof TRequests> =
  GwtIsUnion<TRequest> extends true ? never : GwtRequestFor<TRequests, TRequest>;
export type GwtDefaultRunJsonOptions<TRequest extends string> =
  Omit<Partial<GwtRunJsonOptions<TRequest>>, "request"> & { request?: TRequest };

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
  inspect(options?: GwtInspectOptions): Promise<GwtInspectPayload>;
  validate(options?: GwtValidateOptions): Promise<GwtValidatePayload>;
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

export class GwtProgram<
  TRequests extends object,
  TOutputs extends object,
  TDefaultRequest extends GwtRequestNameFor<TRequests, TOutputs> = GwtRequestNameFor<TRequests, TOutputs>,
  TState extends object = GwtPayload,
> {
  constructor(
    options: string | GwtClient | GwtSpecOptions<TDefaultRequest>,
    specOptions?: GwtSpecRuntimeOptions<TDefaultRequest>,
  );

  client: GwtClient;
  spec: GwtSpec<
    GwtRequestFor<TRequests, TDefaultRequest>,
    GwtOutputFor<TOutputs, TDefaultRequest>,
    TState,
    TDefaultRequest
  >;

  checkOnce(options?: GwtCheckOptions): Promise<GwtCheckPayload>;
  resetCheck(): void;
  runJson<
    TRequest extends GwtRequestNameFor<TRequests, TOutputs>,
  >(
    input: GwtRequestFor<TRequests, TRequest>,
    options: GwtRunJsonOptions<TRequest>,
  ): Promise<GwtSingleExecutionEnvelope<GwtOutputFor<TOutputs, TRequest>, TState>>;
  runJson(
    input: GwtDefaultRequestFor<TRequests, TDefaultRequest>,
    options?: GwtDefaultRunJsonOptions<TDefaultRequest>,
  ): Promise<GwtSingleExecutionEnvelope<GwtOutputFor<TOutputs, TDefaultRequest>, TState>>;
  runRequest(
    requestFile: string,
    options?: GwtRunRequestOptions,
  ): Promise<GwtExecutionEnvelope<GwtOutputFor<TOutputs, GwtRequestNameFor<TRequests, TOutputs>>, TState>>;
  test(options?: GwtTestOptions): Promise<
    GwtExecutionEnvelope<GwtOutputFor<TOutputs, GwtRequestNameFor<TRequests, TOutputs>>, TState>
  >;
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

export function createGwtProgram<
  TRequests extends object,
  TOutputs extends object,
  TDefaultRequest extends GwtRequestNameFor<TRequests, TOutputs> = GwtRequestNameFor<TRequests, TOutputs>,
  TState extends object = GwtPayload,
>(
  options: string | GwtClient | GwtSpecOptions<TDefaultRequest>,
  specOptions?: GwtSpecRuntimeOptions<TDefaultRequest>,
): GwtProgram<TRequests, TOutputs, TDefaultRequest, TState>;

export function checkFile(
  file: string,
  options?: Omit<GwtClientOptions, "file"> & GwtCheckOptions,
): Promise<GwtCheckPayload>;

export function inspectFile(
  file: string,
  options?: Omit<GwtClientOptions, "file"> & GwtInspectOptions,
): Promise<GwtInspectPayload>;

export function validateFile(
  file: string,
  options?: Omit<GwtClientOptions, "file"> & GwtValidateOptions,
): Promise<GwtValidatePayload>;

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
