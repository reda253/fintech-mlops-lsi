export type MlProjectionMethod = 'pca' | 'tsne' | 'umap';

export type MlProjectionView = 'class' | 'cluster' | 'outlier' | 'error' | 'uncertainty';

export interface MlModelInfo {
  name: string;
  version: string;
  algorithm: string;
  alpha: number;
  trained_at: string | null;
  git_commit: string;
  mode: 'real' | 'mock';
}

export interface MlBenchmarkAlgorithmRow {
  id: string;
  shortLabel: string;
  name: string;
  inProduction?: boolean;
  accuracy: number;
  precision: number;
  recall: number;
  f1: number;
  rocAuc: number;
  prAuc: number;
  mcc: number;
  inferenceMs: number;
}

export interface MlConfusionMatrix {
  tn: number;
  fp: number;
  fn: number;
  tp: number;
}

export interface MlConformalSummary {
  targetCoveragePct: number;
  measuredCoveragePct: number;
  reviewSetRatePct: number;
  highUncertaintyRatePct: number;
}

export interface MlStatisticalSummary {
  friedmanPValue: string;
  wilcoxonHolm: string;
  f1ConfidenceInterval95: string;
  genderFairnessGap: string;
}

export interface MlPerformanceReport {
  status: 'ready' | 'demo' | 'unavailable';
  source: string;
  detail: string;
  model: MlModelInfo;
  algorithms: MlBenchmarkAlgorithmRow[];
  confusionMatrix: MlConfusionMatrix;
  conformal: MlConformalSummary;
  statistical: MlStatisticalSummary;
  eceScore: number;
}

export interface MlProjectionPoint {
  id: string;
  x: number;
  y: number;
  label: string;
  is_fraud: 0 | 1;
}

export interface MlProjectionResponse {
  method: MlProjectionMethod;
  view: MlProjectionView;
  model_version: string;
  warning: string;
  sample_size_label: string;
  points: MlProjectionPoint[];
}
