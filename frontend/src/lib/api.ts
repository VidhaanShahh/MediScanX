import axios from 'axios';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const api = axios.create({
  baseURL: API_URL,
});

api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('token');
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

// Types
export interface UserResponse {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface PatientResponse {
  id: string;
  full_name?: string | null;
  anon_code: string;
  age: number | null;
  sex: string | null;
  created_at: string;
}

export interface CaseResponse {
  id: string;
  name?: string | null;
  patient_id: string;
  created_by: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface CaseDetailResponse extends CaseResponse {
  patient: PatientResponse;
  imaging_studies: any[];
  ecg_records: any[];
  predictions: any[];
}

export interface UploadResponse {
  id: string;
  file_type: string;
  sha256: string;
  quality_flag?: string;
  message: string;
}

export interface DiseasePrediction {
  disease: string;
  probability: number;
}

export interface ImagingPredictionResponse {
  predictions: DiseasePrediction[];
  num_classes: number;
  inference_ms: number;
  model_name: string;
  model_version: string;
}

export interface ECGClassPrediction {
  superclass: string;
  probability: number;
  threshold: number;
  above_threshold: boolean;
}

export interface ECGPredictionResponse {
  predictions: ECGClassPrediction[];
  num_classes: number;
  heart_rate_bpm?: number;
  plot_image_base64?: string;
  inference_ms: number;
  model_name: string;
  model_version: string;
}

export interface FusionResponse {
  available: boolean;
  modality_used: string;
  image_score?: number;
  ecg_score?: number;
  fusion_score: number;
  risk_band: string;
  disagreement: boolean;
  difference?: number;
  weight_image: number;
  weight_ecg: number;
  screening_only: boolean;
}

export interface ExplanationItem {
  modality: string;
  explanation_type: string;
  target_class: string;
  file_path: string;
  model_name: string;
  model_version: string;
}

export interface AnalysisResponse {
  case_id: string;
  status: string;
  imaging_predictions?: ImagingPredictionResponse;
  ecg_predictions?: ECGPredictionResponse;
  fusion?: FusionResponse;
  explanations?: ExplanationItem[];
  message: string;
}

export interface ReportResponse {
  id: string;
  case_id: string;
  file_path: string;
  generated_at: string;
  remarks?: string;
}

export interface AuditLogResponse {
  id: string;
  action: string;
  user_id?: string;
  target_id?: string;
  detail?: string;
  timestamp: string;
}

export interface AuditLogPaginated {
  items: AuditLogResponse[];
  total: number;
  page: number;
  page_size: number;
}
