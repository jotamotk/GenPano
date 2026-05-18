const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export interface ProjectLike {
  id?: string | null
}

export interface ProjectBrandContextLike extends ProjectLike {
  primary_brand_id?: number | string | null
  primaryBrandId?: number | string | null
  competitors?: Array<{ brand_id?: number | string | null } | number | string | null> | null
  competitorBrandIds?: Array<number | string | null> | null
}

export function isLiveProjectId(id: string | null | undefined): boolean {
  return !!id && UUID_RE.test(id)
}

export function resolveLiveProjectId(
  liveProjects: ProjectLike[] | null | undefined,
  activeProject?: ProjectLike | null,
): string | null {
  const activeId = activeProject?.id ?? null
  if (isLiveProjectId(activeId)) {
    return activeId
  }

  return liveProjects?.find((project) => isLiveProjectId(project.id))?.id ?? null
}

function sameBrandId(left: number | string | null | undefined, right: number | string): boolean {
  return String(left ?? '') === String(right)
}

export function projectContainsBrand(
  project: ProjectBrandContextLike | null | undefined,
  brandId: number | string | null | undefined,
): boolean {
  if (brandId == null) return false
  if (sameBrandId(project?.primary_brand_id, brandId)) return true
  if (sameBrandId(project?.primaryBrandId, brandId)) return true

  const competitorRows = project?.competitors ?? []
  if (competitorRows.some((row) => {
    if (row == null) return false
    if (typeof row === 'object') return sameBrandId(row.brand_id, brandId)
    return sameBrandId(row, brandId)
  })) {
    return true
  }

  return (project?.competitorBrandIds ?? []).some((id) => sameBrandId(id, brandId))
}

export function findLiveProjectForBrand<T extends ProjectBrandContextLike>(
  liveProjects: T[] | null | undefined,
  brandId: number | string | null | undefined,
): T | null {
  if (brandId == null) return null
  return liveProjects?.find((project) =>
    isLiveProjectId(project.id) && projectContainsBrand(project, brandId)
  ) ?? null
}

export function resolveLiveProjectIdForBrand(
  liveProjects: ProjectBrandContextLike[] | null | undefined,
  activeProject: ProjectBrandContextLike | null | undefined,
  brandId: number | string | null | undefined,
): string | null {
  const brandProject = findLiveProjectForBrand(liveProjects, brandId)
  return brandProject?.id ?? resolveLiveProjectId(liveProjects, activeProject)
}
