# frozen_string_literal: true

# This harness loads the pinned upstream FundingEligibility class directly.
# It supplies only the Rails/model interfaces used by that class so a local
# pilot can compare exact status codes without booting the full application.

require "json"

upstream_root = File.expand_path(ARGV.fetch(0))
service_path = File.join(upstream_root, "app/services/funding_eligibility.rb")
abort "missing upstream service: #{service_path}" unless File.file?(service_path)

module CourseHelper
end

class Object
  def in?(collection)
    collection.include?(self)
  end

  def try(method_name, *args)
    public_send(method_name, *args) if respond_to?(method_name)
  end
end

module Questionnaires
  module WorkSetting
    SCHOOL_SETTINGS = ["school"].freeze
    CHILDCARE_SETTINGS = ["childcare"].freeze
    ANOTHER_SETTING_SETTINGS = ["another_setting"].freeze
    OTHER_SETTINGS = ["other"].freeze
  end
end

class Application
  def self.employment_types
    {
      local_authority_virtual_school: "local_authority_virtual_school",
      hospital_school: "hospital_school",
      young_offender_institution: "young_offender_institution",
      local_authority_supply_teacher: "local_authority_supply_teacher",
      lead_mentor_for_accredited_itt_provider: "lead_mentor_for_accredited_itt_provider",
    }
  end
end

class StubApplications
  def initialize(any)
    @any = any
  end

  def where(*)
    self
  end

  def accepted
    self
  end

  def eligible_for_funding
    self
  end

  def any?
    @any
  end
end

class StubUser
  attr_reader :applications

  def initialize(previously_funded)
    @applications = StubApplications.new(previously_funded)
  end
end

class User
  class << self
    attr_accessor :current

    def find_by(ecf_id:)
      ecf_id
      current
    end
  end
end

class StubCohort
  def initialize(funded)
    @funded = funded
  end

  def funded?
    @funded
  end
end

class StubCourse
  ONLY_PP50 = %w[
    npq-leading-primary-mathematics
    npq-leading-behaviour-culture
    npq-leading-literacy
    npq-leading-teaching
    npq-leading-teaching-development
    npq-executive-leadership
  ].freeze
  LA_NURSERY_APPROVED = %w[npq-senco npq-headship npq-senior-leadership].freeze

  attr_reader :identifier

  def initialize(identifier)
    @identifier = identifier.tr("_", "-")
  end

  def ehco?
    identifier == "npq-early-headship-coaching-offer"
  end

  def eyl?
    identifier == "npq-early-years-leadership"
  end

  def npqltd?
    identifier == "npq-leading-teaching-development"
  end

  def only_pp50?
    ONLY_PP50.include?(identifier)
  end

  def la_nursery_approved?
    LA_NURSERY_APPROVED.include?(identifier)
  end

  def rebranded_alternative_courses
    [self]
  end
end

class School
end

class StubInstitution < School
  def initialize(facts)
    @facts = facts
  end

  def rise?
    @facts.fetch("institution_rise")
  end

  def eligible_establishment?
    @facts.fetch("institution_eligible")
  end

  def pp50?(_work_setting)
    @facts.fetch("institution_pp50")
  end

  def local_authority_nursery_school?
    @facts.fetch("local_authority_nursery")
  end

  def on_childminders_list?
    @facts.fetch("childminder_entitled")
  end
end

load service_path

payload = JSON.parse($stdin.read)
results = payload.map do |item|
  facts = item.fetch("facts")
  User.current = facts.fetch("previously_funded") ? StubUser.new(true) : nil
  institution = facts.fetch("work_policy") == "other" ? nil : StubInstitution.new(facts)

  eligibility = FundingEligibility.new(
    cohort: StubCohort.new(facts.fetch("cohort_funded")),
    institution: institution,
    course: StubCourse.new(facts.fetch("course")),
    inside_catchment: facts.fetch("inside_catchment"),
    user_ecf_id: "local-pilot-user",
    approved_itt_provider: facts.fetch("approved_itt_provider"),
    new_headteacher: facts.fetch("new_headteacher"),
    employment_type: facts.fetch("employment_kind"),
    childminder: facts.fetch("childminder"),
    preschool_class_as_part_of_school: facts.fetch("preschool_class_as_part_of_school"),
    referred_by_return_to_teaching_adviser: facts.fetch("referred_by_return_to_teaching_adviser"),
    work_setting: facts.fetch("work_policy"),
  )

  status = eligibility.funding_eligiblity_status_code
  outcome = if status == FundingEligibility::FUNDED_ELIGIBILITY_RESULT
              "funded"
            elsif [
              FundingEligibility::SUBJECT_TO_REVIEW,
              FundingEligibility::REFERRED_BY_RETURN_TO_TEACHING_ADVISER,
            ].include?(status)
              "subject_to_review"
            else
              "not_funded"
            end

  {
    id: item.fetch("id"),
    outcome: outcome,
    status_code: status.to_s,
    description: FundingEligibility::FUNDING_STATUS_CODE_DESCRIPTIONS.fetch(status).to_s,
  }
end

puts JSON.generate(results)
