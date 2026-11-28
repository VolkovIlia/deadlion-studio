import { basename, dirname, isAbsolute, posix, relative, resolve } from "node:path";

export const documentation = path => /\.(md|rst|png|jpg|svg|ico)$/i.test(path) ||
  /^(?:docs\/.*\.txt|(?:README|CHANGELOG|LICENSE|NOTICE)(?:\.txt)?)$/i.test(path);

export const contains = (scope, path) => scope === "." || scope === path || path.startsWith(scope + "/");
export const scopeList = paths => Array.isArray(paths) && paths.length > 0 && paths.every(p =>
  typeof p === "string" && p.length > 0 && !p.includes("\\") && !p.includes("\0") &&
  !p.startsWith("/") && !p.endsWith("/") &&
  p !== ".." && !p.startsWith("../") && posix.normalize(p) === p);

export const componentManifest = /^(Cargo\.toml|package\.json|go\.mod|pyproject\.toml|pom\.xml|build\.gradle(?:\.kts)?|Makefile)$/;
const publicBoundary = /(?:^|\/)(?:contracts|migrations|schemas|include|interfaces)\/|\.(proto|graphqls?|h|hpp)$/i;

export function changedArea(paths, records) {
  const roots = new Set(Object.keys(records).filter(p => componentManifest.test(basename(p))).map(dirname));
  const componentOf = path => {
    let folder = dirname(path);
    while (folder !== "." && !roots.has(folder)) folder = dirname(folder);
    return folder;
  };
  return paths.map(path => {
    const component = componentOf(path);
    const shared = publicBoundary.test(path) || componentManifest.test(basename(path));
    return { path, component, interface: shared ? path : undefined,
      affectedComponents: shared ? [...new Set([component, ...roots])].sort() : [component] };
  });
}

export function contractCoverage(spec, cwd, root, workload) {
  const files = spec?.candidate_files;
  if (!scopeList(files)) return { type: "performance", workloads: [workload].filter(Boolean) };
  const paths = files.map(p => relative(root, resolve(cwd, p)));
  if (!scopeList(paths) || paths.includes(".") || isAbsolute(relative(root, cwd)))
    return { type: "performance", workloads: [workload].filter(Boolean) };
  return { type: "performance", paths, exact: true, workloads: [workload].filter(Boolean) };
}

export function coverageFor(area, checks) {
  const functional = checks.flatMap(check => {
    const claim = check.coverage;
    if (check.status !== "PASS" || !claim || !["functional", "oracle"].includes(claim.type)) return [];
    return [claim];
  });
  return area.filter(row => !documentation(row.path)).map(row => {
    const covered = row.interface
      ? row.affectedComponents.every(component => functional.some(({ paths, exact }) =>
        !exact && paths?.some(scope => contains(scope, component))))
      : functional.some(({ paths, exact }) =>
        paths?.some(scope => exact ? scope === row.path : contains(scope, row.path)));
    return { ...row, requirement: "functional", status: covered ? "VERIFIED" : "NOT VERIFIED" };
  });
}
