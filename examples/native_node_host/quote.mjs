import { fileURLToPath } from 'node:url';
import { runNativeRequest, stringifyExact } from './native.mjs';

const executable = process.argv[2];
if (!executable) throw new Error('Usage: node quote.mjs /absolute/path/to/gwt');
const {execution} = await runNativeRequest({
  executable,
  program: fileURLToPath(new URL('../../crates/gwt-core/tests/fixtures/invoice.gwt', import.meta.url)),
  request: 'price invoice',
  input: {invoice: {unit_price: '0.01', quantity: 9007199254740993n}},
});
if (!execution.ok) {
  console.error(stringifyExact(execution.diagnostic));
  process.exitCode = 1;
} else {
  // The total remains decimal text. Application I/O belongs here, outside GWT.
  console.log(stringifyExact(execution.result));
}
