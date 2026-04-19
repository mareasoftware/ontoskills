import { useState, useMemo } from 'react';

interface TreeNode {
  name: string;
  fullPath?: string;
  children: Map<string, TreeNode>;
  isFile: boolean;
}

function buildTree(originalPaths: string[], strippedPaths: string[]): TreeNode {
  const root: TreeNode = { name: '', children: new Map(), isFile: false };
  for (let j = 0; j < strippedPaths.length; j++) {
    const stripped = strippedPaths[j];
    const original = originalPaths[j];
    const parts = stripped.split('/');
    let node = root;
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const isFile = i === parts.length - 1;
      if (!node.children.has(part)) {
        node.children.set(part, { name: part, fullPath: isFile ? original : undefined, children: new Map(), isFile });
      }
      node = node.children.get(part)!;
    }
  }
  return root;
}

function FolderIcon({ open }: { open: boolean }) {
  return open
    ? <svg className="w-3.5 h-3.5 text-[#dba32c] shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" clipRule="evenodd" /></svg>
    : <svg className="w-3.5 h-3.5 text-[#8a8a8a] shrink-0" fill="currentColor" viewBox="0 0 20 20"><path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v2H2V6z" /><path fillRule="evenodd" d="M2 10h16v4a2 2 0 01-2 2H4a2 2 0 01-2-2v-4z" clipRule="evenodd" /></svg>;
}

function FileIcon({ name }: { name: string }) {
  const color = name.endsWith('.ttl') ? '#52c7e8' : '#666';
  return <svg className="w-3.5 h-3.5 shrink-0" style={{ color }} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>;
}

function Chevron({ open }: { open: boolean }) {
  return <svg className={`w-3 h-3 text-[#666] shrink-0 transition-transform ${open ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>;
}

function FileTreeLevel({ node, depth, onTtlClick, githubBase }: {
  node: TreeNode;
  depth: number;
  onTtlClick: (path: string) => void;
  githubBase: string;
}) {
  const [open, setOpen] = useState(depth === 0);
  const entries = useMemo(() => {
    return [...node.children.values()].sort((a, b) => {
      if (a.isFile !== b.isFile) return a.isFile ? 1 : -1;
      return a.name.localeCompare(b.name);
    });
  }, [node.children]);

  if (!entries.length) return null;

  return (
    <>
      {depth > 0 && (
        <button onClick={() => setOpen(!open)} className="flex items-center gap-2 w-full px-2 py-1.5 rounded-md hover:bg-white/[0.04] transition-colors text-left" style={{ paddingLeft: `${depth * 16 + 20}px` }}>
          <Chevron open={open} />
          <FolderIcon open={open} />
          <span className={`text-xs sm:text-sm font-medium truncate ${open ? 'text-[#d4d4d4]' : 'text-[#8a8a8a]'}`}>{node.name}</span>
        </button>
      )}
      {(depth === 0 || open) && entries.map(child => {
        if (!child.isFile) return <FileTreeLevel key={child.name} node={child} depth={depth + 1} onTtlClick={onTtlClick} githubBase={githubBase} />;
        const isTtl = child.name.endsWith('.ttl');
        const isMain = child.fullPath?.endsWith('/ontoskill.ttl');
        const paddingLeft = `${(depth + 1) * 16 + 20}px`;
        const ghUrl = `${githubBase}/${child.fullPath}`;

        if (isTtl) return (
          <button key={child.fullPath} onClick={() => child.fullPath && onTtlClick(child.fullPath)} className="flex items-center gap-2 w-full px-2 py-1.5 rounded-md hover:bg-[#52c7e8]/[0.04] transition-colors text-left group" style={{ paddingLeft }}>
            <FileIcon name={child.name} />
            <span className="font-mono text-xs sm:text-sm text-[#d4d4d4] group-hover:text-[#52c7e8] truncate">{child.name}</span>
            {isMain && <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#52c7e8]/10 text-[#52c7e8] font-medium shrink-0">main</span>}
            <svg className="w-3 h-3 text-[#444] group-hover:text-[#52c7e8] shrink-0 ml-auto transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" /></svg>
          </button>
        );

        return (
          <a key={child.fullPath} href={ghUrl} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 w-full px-2 py-1.5 rounded-md hover:bg-white/[0.03] transition-colors text-left group" style={{ paddingLeft }}>
            <FileIcon name={child.name} />
            <span className="font-mono text-xs sm:text-sm text-[#666] group-hover:text-[#8a8a8a] truncate">{child.name}</span>
            <svg className="w-3 h-3 text-[#333] group-hover:text-[#666] shrink-0 ml-auto transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
          </a>
        );
      })}
    </>
  );
}

export function FileTree({ paths, basePath, onTtlClick, githubBase }: {
  paths: string[];
  basePath: string;
  onTtlClick: (path: string) => void;
  githubBase: string;
}) {
  const tree = useMemo(() => {
    const stripped = paths.map(p => p.startsWith(basePath + '/') ? p.slice(basePath.length + 1) : p);
    return buildTree(paths, stripped);
  }, [paths, basePath]);

  return <FileTreeLevel node={tree} depth={0} onTtlClick={onTtlClick} githubBase={githubBase} />;
}
