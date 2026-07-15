# frozen_string_literal: true

require "bigdecimal"
require "json"

class Object
  def present?
    !nil? && self != false && (!respond_to?(:empty?) || !empty?)
  end
end

class EligibilityErrors
  attr_reader :codes

  def initialize
    @codes = []
  end

  def add(_field, error)
    @codes << error.fetch(:code).to_s
  end

  def empty?
    @codes.empty?
  end
end

class PromotionRule
  def self.preference(name, _type, default:, **_options)
    attr_accessor "preferred_#{name}"
  end

  attr_reader :eligibility_errors

  def initialize
    @eligibility_errors = EligibilityErrors.new
  end

  def eligibility_error_message(code, amount:)
    {code: code, amount: amount}
  end
end

module Spree
  def self.t(key)
    key.to_s
  end

  class Money
    def initialize(amount, currency:)
      @amount = amount
      @currency = currency
    end

    def to_s
      "#{@currency}:#{@amount}"
    end
  end

  class Order
    attr_reader :item_total, :currency

    def initialize(item_total, currency: "USD")
      @item_total = BigDecimal(item_total.to_s)
      @currency = currency
    end
  end

  class Promotion
    module Rules
    end
  end
end

upstream_root = ARGV.fetch(0)
load File.join(upstream_root, "spree/core/app/models/spree/promotion/rules/item_total.rb")

results = JSON.parse($stdin.read).map do |input|
  rule = Spree::Promotion::Rules::ItemTotal.new
  rule.preferred_amount_min = input.fetch("amount_min")
  rule.preferred_operator_min = input.fetch("minimum_mode")
  rule.preferred_amount_max = input.fetch("has_maximum") ? input.fetch("amount_max") : nil
  rule.preferred_operator_max = input.fetch("maximum_mode")
  order = Spree::Order.new(input.fetch("item_total"))
  eligible = rule.eligible?(order)
  {
    id: input.fetch("id"),
    eligible: eligible,
    first_error: rule.eligibility_errors.codes.first || "none",
    error_count: rule.eligibility_errors.codes.length
  }
end

puts JSON.generate(results)
