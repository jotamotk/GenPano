const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export interface ProjectLike {
  id?: string | null
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
