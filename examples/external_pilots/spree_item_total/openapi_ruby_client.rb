# frozen_string_literal: true

require "json"
require "uri"
require "gwt_spree_client"

base_url = URI(ARGV.fetch(0))
host = base_url.default_port == base_url.port ? base_url.host : "#{base_url.host}:#{base_url.port}"
GwtSpreeClient.configure do |config|
  config.scheme = base_url.scheme
  config.host = host
  config.base_path = base_url.path
  config.ignore_operation_servers = true
end

api = GwtSpreeClient::DefaultApi.new
cases = JSON.parse($stdin.read)
results = cases.map do |item|
  facts_input = item.fetch("facts").dup
  has_maximum = facts_input.delete("has_maximum")
  facts_input.delete("amount_max") unless has_maximum
  facts = GwtSpreeClient::ItemTotalFacts.new(facts_input)
  if !has_maximum && facts.to_hash.key?(:amount_max)
    raise "#{item.fetch('id')}: generated client did not preserve omitted amount_max"
  end

  request = GwtSpreeClient::AssessItemTotalEligibilityRequest.new(facts: facts)
  response = api.assess_item_total_eligibility(request)
  decision = response.decision
  actual = {
    "eligible" => decision.eligible,
    "first_error" => decision.first_error,
    "error_count" => decision.error_count
  }
  expected = item.fetch("expected")
  raise "#{item.fetch('id')}: HTTP #{actual.inspect}, expected #{expected.inspect}" unless actual == expected

  {"id" => item.fetch("id"), "decision" => actual}
end

puts JSON.generate(results)
