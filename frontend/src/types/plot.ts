export type SoilType =
  | 'red_yellow_podzolic'
  | 'reddish_brown_earth'
  | 'low_humic_gley'
  | 'regosols'
  | 'immature_brown_loam'
  | 'coco_peat'
  | 'soil_based_mix'
  | 'compost_mix'
  | 'other'

export interface Plot {
  id: string
  tenant_id: string
  farm_id: string
  name: string
  area_ha: number
  latitude: number | null
  longitude: number | null
  crop: string | null
  stage: string | null
  soil_type: SoilType
  created_at: string
}

export interface CreatePlotInput {
  name: string
  farm_id: string
  area_ha: number
  crop?: string | null
  stage?: string | null
  soil_type: SoilType
  latitude?: number | null
  longitude?: number | null
}

// Human-readable labels for the soil type dropdown
export const SOIL_TYPE_LABELS: Record<SoilType, string> = {
  red_yellow_podzolic: 'Red-Yellow Podzolic',
  reddish_brown_earth: 'Reddish Brown Earth',
  low_humic_gley: 'Low Humic Gley',
  regosols: 'Regosols (Coastal Sand)',
  immature_brown_loam: 'Immature Brown Loam',
  coco_peat: 'Coco Peat (Substrate)',
  soil_based_mix: 'Soil-Based Mix',
  compost_mix: 'Compost Mix',
  other: 'Other',
}

// Common growth stages
export const GROWTH_STAGES = [
  'seedling',
  'vegetative',
  'flowering',
  'fruiting',
  'maturity',
  'harvest',
  'fallow',
] as const