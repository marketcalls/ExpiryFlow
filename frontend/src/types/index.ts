export interface ConfigExistsResponse {
  exists: boolean
  client_id: string | null
}

export interface ConfigCreate {
  client_id: string
  api_key: string
  api_secret: string
}

export interface ConfigResponse {
  client_id: string
  api_key_masked: string
  api_secret_masked: string
  created_at: string
  updated_at: string
}

export interface LoginRequest {
  pin: string
  totp: string
}

export interface LoginResponse {
  dhan_client_id: string
  dhan_client_name: string
  access_token: string
  expiry_time: string
}

export interface SessionStatusResponse {
  active: boolean
  dhan_client_id: string | null
  dhan_client_name: string | null
  expiry_time: string | null
  is_expired: boolean
}

export interface MessageResponse {
  message: string
}

// --- Download types ---
export interface DownloadRequest {
  underlying_scrip: string
  exchange_segment: string
  instrument: string
  security_id: number
  option_type: string
  expiry_flags: string[]
  expiry_codes: number[]
  strike_range: number
  interval: string
  from_date: string
  to_date: string
}

export interface DownloadProgress {
  job_id: string
  status: "pending" | "running" | "completed" | "failed" | "cancelled"
  total_requests: number
  completed_requests: number
  skipped_requests: number
  failed_requests: number
  rows_downloaded: number
  error_message: string | null
  started_at: string | null
  completed_at: string | null
}

export interface DownloadHistoryItem {
  underlying_scrip: string
  expiry_flag: string
  expiry_code: number
  interval: string
  strike_label: string
  option_type: string
  from_date: string
  to_date: string
  row_count: number
  downloaded_at: string
}

export interface DownloadHistoryResponse {
  items: DownloadHistoryItem[]
  total: number
}

export interface RateLimitStatus {
  requests_today: number
  daily_limit: number
  daily_remaining: number
}

// --- Straddle types ---
export interface StraddleUnderlyingsResponse {
  underlyings: string[]
}

export interface StraddleDatesResponse {
  dates: string[]
}

export interface StraddleRow {
  timestamp: string
  strike_price: number | null
  ce_open: number | null
  ce_high: number | null
  ce_low: number | null
  ce_close: number | null
  pe_open: number | null
  pe_high: number | null
  pe_low: number | null
  pe_close: number | null
  combined_premium: number | null
  ce_iv: number | null
  pe_iv: number | null
  ce_volume: number | null
  pe_volume: number | null
  ce_oi: number | null
  pe_oi: number | null
  spot: number | null
}

export interface StraddleDataResponse {
  rows: StraddleRow[]
  total: number
}
