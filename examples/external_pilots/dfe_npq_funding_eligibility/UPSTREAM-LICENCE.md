# Upstream attribution and licence

This independent local pilot was derived by reading the following files in
[`DFE-Digital/npq-registration`](https://github.com/DFE-Digital/npq-registration)
at commit `f3601047213660121a5b8e0850c8ecef798f8e03`:

- `app/services/funding_eligibility.rb`
- `spec/services/funding_eligibility_scenarios_spec.rb`
- `spec/fixtures/scenarios/eligibility_testing_scenarios.csv`

The upstream repository is distributed under this licence:

> MIT License
>
> Copyright (c) 2018 Department for Education - Digital
>
> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to deal
> in the Software without restriction, including without limitation the rights
> to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
> copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all
> copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
> OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
> SOFTWARE.

The pilot does not copy the upstream Ruby implementation or CSV fixture into
this repository. Its GWT rules and Python boundary adapter are an independent,
scoped expression of the observed decision behavior. The comparison command
requires an explicit path to a separately obtained upstream fixture.
