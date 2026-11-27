import { apiRequest } from './client';
import type {
  MlBenchmarkAlgorithmRow,
  MlModelInfo,
  MlPerformanceReport,
  MlProjectionMethod,
  MlProjectionPoint,
  MlProjectionResponse,
  MlProjectionView,
} from '@/types/ml';

export const DEFAULT_MODEL_INFO: MlModelInfo = {
  name: 'fraud-detector',
  version: '8',
  algorithm: 'XGBoost',
  alpha: 0.05,
  trained_at: '2026-10-02T14:08:00Z',
  git_commit: '3f9a1c2',
  mode: 'mock',
};

export const DEFAULT_BENCHMARK_ALGORITHMS: MlBenchmarkAlgorithmRow[] = [
  {
    id: 'lr',
    shortLabel: 'LR',
    name: 'Régression logistique',
    accuracy: 0.996,
    precision: 0.861,
    recall: 0.824,
    f1: 0.842,
    rocAuc: 0.951,
    prAuc: 0.871,
    mcc: 0.84,
    inferenceMs: 0.2,
  },
  {
    id: 'rf',
    shortLabel: 'RF',
    name: 'Random Forest',
    accuracy: 0.998,
    precision: 0.928,
    recall: 0.894,
    f1: 0.911,
    rocAuc: 0.981,
    prAuc: 0.934,
    mcc: 0.91,
    inferenceMs: 6.1,
  },
  {
    id: 'xgb',
    shortLabel: 'XGB',
    name: 'Gradient Boosting (XGBoost)',
    inProduction: true,
    accuracy: 0.998,
    precision: 0.918,
    recall: 0.93,
    f1: 0.924,
    rocAuc: 0.987,
    prAuc: 0.957,
    mcc: 0.923,
    inferenceMs: 2.4,
  },
  {
    id: 'svm',
    shortLabel: 'SVM',
    name: 'SVM (Nystroem + LinearSVC)',
    accuracy: 0.997,
    precision: 0.902,
    recall: 0.873,
    f1: 0.887,
    rocAuc: 0.968,
    prAuc: 0.912,
    mcc: 0.886,
    inferenceMs: 0.9,
  },
  {
    id: 'mlp',
    shortLabel: 'MLP',
    name: 'MLP',
    accuracy: 0.998,
    precision: 0.913,
    recall: 0.894,
    f1: 0.903,
    rocAuc: 0.976,
    prAuc: 0.928,
    mcc: 0.902,
    inferenceMs: 1.3,
  },
];

export const DEFAULT_PERFORMANCE_REPORT: MlPerformanceReport = {
  status: 'demo',
  source: 'demo',
  detail:
    "Valeurs illustratives de la maquette. La structure réelle est fournie par GET /api/v1/ml/performance (benchmark, tests statistiques, test final avec intervalles de confiance, équité) ; aucun résultat ML définitif n'est affiché ici.",
  model: DEFAULT_MODEL_INFO,
  algorithms: DEFAULT_BENCHMARK_ALGORITHMS,
  confusionMatrix: {
    tn: 23917,
    fp: 83,
    fn: 70,
    tp: 930,
  },
  conformal: {
    targetCoveragePct: 95.0,
    measuredCoveragePct: 95.3,
    reviewSetRatePct: 2.0,
    highUncertaintyRatePct: 1.6,
  },
  statistical: {
    friedmanPValue: 'p < 0,001',
    wilcoxonHolm: 'XGBoost > SVM, LR',
    f1ConfidenceInterval95: '[0,917 ; 0,931]',
    genderFairnessGap: 'écart de rappel 0,8 pt',
  },
  eceScore: 0.012,
};

function seededRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (1664525 * state + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

function getLabelForView(
  view: MlProjectionView,
  isFraud: 0 | 1,
  clusterIdx: number,
  randVal: number,
): string {
  switch (view) {
    case 'class':
      return isFraud === 1 ? 'FRAUD' : 'LEGIT';
    case 'cluster':
      return isFraud === 1 ? 'CLUSTER_FRAUD' : `CLUSTER_${(clusterIdx % 3) + 1}`;
    case 'outlier':
      return isFraud === 1 || randVal > 0.84 ? 'ANOMALIE' : 'NORMAL';
    case 'error':
      if (isFraud === 1) return randVal > 0.18 ? 'VP' : 'FN';
      return randVal > 0.91 ? 'FP' : 'VN';
    case 'uncertainty':
    default:
      if (isFraud === 1) return 'FRAUD';
      return randVal > 0.8 ? 'ELEVEE' : 'FAIBLE';
  }
}

export function generateDeterministicProjectionPoints(
  method: MlProjectionMethod,
  view: MlProjectionView,
): MlProjectionPoint[] {
  const methodSeed = method === 'pca' ? 101 : method === 'tsne' ? 202 : 303;
  const viewSeed =
    view === 'class'
      ? 11
      : view === 'cluster'
        ? 22
        : view === 'outlier'
          ? 33
          : view === 'error'
            ? 44
            : 55;
  const rand = seededRandom(methodSeed * 31 + viewSeed);

  const legitCenters: Array<[number, number]> =
    method === 'pca'
      ? [
          [-6.5, -2.0],
          [1.5, 4.2],
          [7.8, -3.5],
        ]
      : method === 'tsne'
        ? [
            [-18.0, 11.5],
            [-16.5, -11.0],
            [11.5, 13.0],
            [14.0, -11.5],
          ]
        : [
            [-14.5, 10.0],
            [2.0, 14.0],
            [-8.0, -12.5],
            [13.5, -9.0],
          ];

  const fraudCenters: Array<[number, number]> =
    method === 'pca'
      ? [
          [-19.5, -12.5],
          [18.5, 11.0],
        ]
      : method === 'tsne'
        ? [
            [-1.5, -1.2],
            [22.0, -1.8],
          ]
        : [
            [-2.5, 1.5],
            [16.5, -2.5],
          ];

  const points: MlProjectionPoint[] = [];

  // Featured reference point matching Mockup 12 tooltip: x 12,4 · y -3,1, label ELEVEE, is_fraud 0
  points.push({
    id: `${method}-${view}-featured`,
    x: 12.4,
    y: -3.1,
    label: view === 'uncertainty' ? 'ELEVEE' : getLabelForView(view, 0, 1, 0.93),
    is_fraud: 0,
  });

  // Legitimate points across clusters
  for (let i = 0; i < 150; i += 1) {
    const center = legitCenters[i % legitCenters.length] ?? [0, 0];
    const angle = rand() * Math.PI * 2;
    const radius = (rand() + rand()) * (method === 'pca' ? 6.2 : 5.4);
    const x = Number((center[0] + Math.cos(angle) * radius).toFixed(1));
    const y = Number((center[1] + Math.sin(angle) * radius).toFixed(1));
    const r = rand();
    points.push({
      id: `${method}-${view}-legit-${i}`,
      x,
      y,
      label: getLabelForView(view, 0, i, r),
      is_fraud: 0,
    });
  }

  // Fraud points in dedicated clusters
  for (let i = 0; i < 34; i += 1) {
    const center = fraudCenters[i % fraudCenters.length] ?? [0, 0];
    const angle = rand() * Math.PI * 2;
    const radius = (rand() + rand()) * 3.1;
    const x = Number((center[0] + Math.cos(angle) * radius).toFixed(1));
    const y = Number((center[1] + Math.sin(angle) * radius).toFixed(1));
    const r = rand();
    points.push({
      id: `${method}-${view}-fraud-${i}`,
      x,
      y,
      label: getLabelForView(view, 1, i, r),
      is_fraud: 1,
    });
  }

  return points;
}

export async function fetchMlPerformanceReport(): Promise<MlPerformanceReport> {
  try {
    const [modelRes, perfRes] = await Promise.allSettled([
      apiRequest<Partial<MlModelInfo>>('/ml/model'),
      apiRequest<Record<string, unknown>>('/ml/performance'),
    ]);

    const modelData = modelRes.status === 'fulfilled' ? modelRes.value : null;
    const perfData = perfRes.status === 'fulfilled' ? perfRes.value : null;

    if (!modelData && !perfData) {
      return DEFAULT_PERFORMANCE_REPORT;
    }

    const mergedModel: MlModelInfo = {
      name: typeof modelData?.name === 'string' ? modelData.name : DEFAULT_MODEL_INFO.name,
      version:
        typeof modelData?.version === 'string' && modelData.version !== 'mock'
          ? modelData.version
          : DEFAULT_MODEL_INFO.version,
      algorithm:
        typeof modelData?.algorithm === 'string' && modelData.algorithm !== 'heuristic-mock'
          ? modelData.algorithm
          : DEFAULT_MODEL_INFO.algorithm,
      alpha: typeof modelData?.alpha === 'number' ? modelData.alpha : DEFAULT_MODEL_INFO.alpha,
      trained_at:
        typeof modelData?.trained_at === 'string'
          ? modelData.trained_at
          : DEFAULT_MODEL_INFO.trained_at,
      git_commit:
        typeof modelData?.git_commit === 'string' && modelData.git_commit !== 'unknown'
          ? modelData.git_commit
          : DEFAULT_MODEL_INFO.git_commit,
      mode: modelData?.mode === 'real' ? 'real' : 'mock',
    };

    const rawStatus = perfData?.status;
    const status: MlPerformanceReport['status'] =
      rawStatus === 'ready' || rawStatus === 'unavailable' ? rawStatus : 'demo';

    return {
      ...DEFAULT_PERFORMANCE_REPORT,
      status,
      source: typeof perfData?.source === 'string' ? perfData.source : DEFAULT_PERFORMANCE_REPORT.source,
      detail: DEFAULT_PERFORMANCE_REPORT.detail,
      model: mergedModel,
    };
  } catch {
    return DEFAULT_PERFORMANCE_REPORT;
  }
}

export async function fetchMlProjection(
  method: MlProjectionMethod,
  view: MlProjectionView,
): Promise<MlProjectionResponse> {
  const defaultPoints = generateDeterministicProjectionPoints(method, view);
  const defaultWarning =
    "Avec t-SNE et UMAP, les distances entre groupes et la taille des groupes n'ont pas de signification quantitative : seule la proximité locale est interprétable. Projection calculée pour la version 8 du modèle.";

  try {
    interface RawVizPoint {
      x?: number;
      y?: number;
      label?: string | null;
      is_fraud?: number | null;
    }
    const raw = await apiRequest<{
      method?: string;
      view?: string;
      model_version?: string;
      warning?: string;
      points?: RawVizPoint[];
    }>(`/ml/viz/${method}`, {
      method: 'GET',
      query: { view },
    });

    const apiPoints: RawVizPoint[] = Array.isArray(raw?.points) ? raw.points : [];
    const normalizedPoints: MlProjectionPoint[] =
      apiPoints.length > 20
        ? apiPoints.map((pt: RawVizPoint, idx: number) => ({
            id: `${method}-${view}-api-${idx}`,
            x: typeof pt.x === 'number' ? Number(pt.x.toFixed(1)) : 0,
            y: typeof pt.y === 'number' ? Number(pt.y.toFixed(1)) : 0,
            label: typeof pt.label === 'string' && pt.label ? pt.label : 'FAIBLE',
            is_fraud: pt.is_fraud === 1 ? 1 : 0,
          }))
        : defaultPoints;

    return {
      method,
      view,
      model_version:
        typeof raw?.model_version === 'string' && raw.model_version !== 'mock'
          ? raw.model_version
          : '8',
      warning: defaultWarning,
      sample_size_label: '~20 000 points',
      points: normalizedPoints,
    };
  } catch {
    return {
      method,
      view,
      model_version: '8',
      warning: defaultWarning,
      sample_size_label: '~20 000 points',
      points: defaultPoints,
    };
  }
}
