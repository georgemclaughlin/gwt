// Generated from examples/vendor_onboarding/rules.gwt. Do not edit by hand.

export interface VendorDocument {
  name: string;
  status: "provided" | "missing" | "expired";
}

export interface VendorRiskSignal {
  name: string;
  severity: "low" | "medium" | "high";
  points: number;
}

export interface VendorRequest {
  vendor_name: string;
  country: string;
  annual_spend: number;
  handles_customer_data: boolean;
  stores_payment_data: boolean;
  documents: VendorDocument[];
  risk_signals: VendorRiskSignal[];
}

export interface VendorDecision {
  required_document_count: number;
  missing_document_count: number;
  expired_document_count: number;
  high_signal_count: number;
  risk_points: number;
  missing_requirements: string[];
  reasons: string[];
  data_review_required: boolean;
  tier: "new" | "standard" | "critical";
  status: "new" | "approved" | "needs_review" | "rejected";
  reason: "new" | "ready_to_onboard" | "manual_review_required" | "high_risk_signal" | "risk_too_high";
}

export interface ReviewVendorRequest {
  vendor: VendorRequest;
}

export interface ReviewVendorOutput {
  decision: VendorDecision;
}

export type GwtRequestName = "review vendor";

export interface GwtRequests {
  "review vendor": ReviewVendorRequest;
}

export interface GwtOutputs {
  "review vendor": ReviewVendorOutput;
}

export type GwtRequest = GwtRequests[GwtRequestName];
export type GwtOutput = GwtOutputs[GwtRequestName];
