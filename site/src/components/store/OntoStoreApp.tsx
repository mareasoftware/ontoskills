import { useState, useEffect, useCallback, useMemo } from 'react';
import type { Skill, PackageManifest, ViewMode } from './types';
import { translations } from './i18n';
import { STORE_INDEX_URL, normSkill } from './helpers';
import { StoreView } from './views/StoreView';
import { AuthorView } from './views/AuthorView';
import { PackageView } from './views/PackageView';
import { SkillDetailView } from './views/SkillDetailView';

export default function OntoStoreApp({ lang = 'en' }: { lang?: string }) {
  const t = translations[lang as keyof typeof translations] || translations.en;
  const prefix = lang === 'zh' ? '/zh/ontostore' : '/ontostore';

  useEffect(() => {
    const el = document.getElementById('ontostore-loader');
    if (el) el.remove();
  }, []);

  // Patch Header language toggles to preserve SPA sub-routes
  useEffect(() => {
    const toggles = document.querySelectorAll<HTMLElement>('.lang-toggle');
    if (toggles.length === 0) return;
    const handler = (e: Event) => {
      const me = e as MouseEvent;
      if (me.button !== 0 || me.metaKey || me.ctrlKey || me.shiftKey) return;
      e.preventDefault();
      const currentPath = window.location.pathname;
      const r = new URLSearchParams(window.location.search).get('r');
      const subpath = r || currentPath.replace(prefix, '').replace(/^\//, '');
      const target = lang === 'en' ? '/zh/ontostore/' : '/ontostore/';
      window.location.href = subpath
        ? `${target}?r=${encodeURIComponent(subpath)}`
        : target;
    };
    toggles.forEach(el => { el.onclick = handler; });
    return () => { toggles.forEach(el => { el.onclick = null; }); };
  }, [lang, prefix]);

  const [skills, setSkills] = useState<Skill[]>([]);
  const [packages, setPackages] = useState<PackageManifest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const [viewMode, setViewMode] = useState<ViewMode>('store');
  const [authorId, setAuthorId] = useState('');
  const [pkgId, setPkgId] = useState('');
  const [skillId, setSkillId] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [filterAuthor, setFilterAuthor] = useState('');
  const [filterCategory, setFilterCategory] = useState('');
  const [filterTier, setFilterTier] = useState('');
  const [filterSort, setFilterSort] = useState('az');
  const [visibleCount, setVisibleCount] = useState(20);

  const meta = useMemo(() => ({
    authors: [...new Set(skills.map(s => s.author))].sort(),
    categories: [...new Set(skills.map(s => s.category).filter(Boolean))].sort(),
    trustTiers: [...new Set(skills.map(s => s.trustTier))].sort(),
  }), [skills]);

  const filteredSkills = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return skills.filter(s => {
      if (q) {
        const h = [s.packageId, s.skillId, s.qualifiedId, s.description, s.aliases.join(' '), s.category, s.intents.join(' ')].join(' ').toLowerCase();
        if (!h.includes(q)) return false;
      }
      if (filterAuthor && s.author !== filterAuthor) return false;
      if (filterCategory && s.category !== filterCategory) return false;
      if (filterTier && s.trustTier !== filterTier) return false;
      return true;
    }).sort((a, b) => filterSort === 'za' ? b.qualifiedId.localeCompare(a.qualifiedId) : a.qualifiedId.localeCompare(b.qualifiedId));
  }, [skills, searchQuery, filterAuthor, filterCategory, filterTier, filterSort]);

  useEffect(() => {
    const controller = new AbortController();
    const signal = controller.signal;
    const load = async () => {
      try {
        const res = await fetch(STORE_INDEX_URL, { mode: 'cors', headers: { Accept: 'application/json' }, signal });
        if (!res.ok) throw new Error(`Index failed: ${res.status}`);
        const data = await res.json();
        const results = await Promise.allSettled(
          (data.packages || []).map(async (entry: any) => {
            const url = new URL(entry.manifest_path, STORE_INDEX_URL);
            if (url.origin !== new URL(STORE_INDEX_URL).origin) throw new Error('Cross-origin manifest');
            const r = await fetch(url.toString(), { mode: 'cors', headers: { Accept: 'application/json' }, signal });
            if (!r.ok) throw new Error(`Manifest failed: ${r.status}`);
            return r.json();
          })
        );
        if (signal.aborted) return;
        const manifests = results.filter(r => r.status === 'fulfilled').map(r => (r as any).value);
        if (manifests.length === 0 && results.some(r => r.status === 'rejected')) {
          setError(true); setLoading(false); return;
        }
        setPackages(manifests);
        const newSkills = manifests.flatMap(pkg => (pkg.skills || []).map((s: any) => normSkill(pkg, s)));
        newSkills.sort((a, b) => a.qualifiedId.localeCompare(b.qualifiedId));
        setSkills(newSkills);
        setLoading(false);
      } catch (e) {
        if (signal.aborted) return;
        setError(true); setLoading(false);
      }
    };
    load();
    return () => { controller.abort(); };
  }, []);

  useEffect(() => {
    const parse = () => {
      let path = window.location.pathname.replace(/\/$/, '');
      // Check URL param redirect (?r=...) — set by 404 page for deep links
      try {
        const params = new URLSearchParams(window.location.search);
        const r = params.get('r');
        if (r && /^[a-zA-Z0-9/_-]+$/.test(r)) {
          const full = prefix + '/' + r.replace(/^\//, '');
          history.replaceState(null, '', full);
          path = full;
        }
      } catch {}
      const storePath = path.replace(prefix, '').replace(/^\//, '');
      const segments = storePath ? storePath.split('/') : [];
      if (segments.length === 0) { setViewMode('store'); }
      else if (segments.length === 1) { setViewMode('author'); setAuthorId(segments[0]); }
      else if (segments.length === 2) { setViewMode('package'); setPkgId(segments.join('/')); }
      else { setViewMode('skill'); setPkgId(segments.slice(0, 2).join('/')); setSkillId(segments.slice(2).join('/')); }
    };
    parse();
    window.addEventListener('popstate', parse);
    return () => window.removeEventListener('popstate', parse);
  }, [prefix]);

  const navigate = useCallback((href: string) => {
    history.pushState(null, '', href);
    window.dispatchEvent(new PopStateEvent('popstate'));
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    window.scrollTo({ top: 0, behavior: reduced ? 'auto' : 'smooth' });
  }, []);

  useEffect(() => {
    setVisibleCount(20);
    setSearchQuery('');
    setFilterAuthor('');
    setFilterCategory('');
    setFilterTier('');
    setFilterSort('az');
  }, [viewMode]);

  useEffect(() => {
    const base = lang === 'zh' ? 'OntoStore — 浏览本体技能' : 'OntoStore — Browse Ontological Skills';
    if (viewMode === 'store') document.title = base;
    else if (viewMode === 'author') document.title = `${authorId} — ${base}`;
    else if (viewMode === 'package') document.title = `${pkgId} — ${base}`;
    else if (viewMode === 'skill') document.title = `${skillId} — ${base}`;
  }, [viewMode, authorId, pkgId, skillId, lang]);

  if (error) {
    return (
      <div className="text-center py-20">
        <p className="text-[#d4d4d4] mb-4">{t.unableToLoad}</p>
        <button onClick={() => window.location.reload()} className="px-4 py-2 rounded-lg bg-[#52c7e8]/10 text-[#52c7e8] hover:bg-[#52c7e8]/20 transition-colors">{t.retry}</button>
      </div>
    );
  }

  return (
    <div className="ontoskills-store-root overflow-x-hidden pt-8 sm:pt-10">
      <div className="store-glow" />
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 relative">
        {viewMode === 'store' && <StoreView loading={loading} filteredSkills={filteredSkills} meta={meta} t={t} prefix={prefix} navigate={navigate} searchQuery={searchQuery} setSearchQuery={setSearchQuery} filterAuthor={filterAuthor} setFilterAuthor={setFilterAuthor} filterCategory={filterCategory} setFilterCategory={setFilterCategory} filterTier={filterTier} setFilterTier={setFilterTier} filterSort={filterSort} setFilterSort={setFilterSort} visibleCount={visibleCount} setVisibleCount={setVisibleCount} lang={lang} />}
        {viewMode === 'author' && <AuthorView loading={loading} skills={skills} authorId={authorId} t={t} prefix={prefix} navigate={navigate} />}
        {viewMode === 'package' && <PackageView loading={loading} skills={skills} packages={packages} pkgId={pkgId} t={t} prefix={prefix} navigate={navigate} />}
        {viewMode === 'skill' && <SkillDetailView skills={skills} packages={packages} pkgId={pkgId} skillId={skillId} t={t} prefix={prefix} navigate={navigate} />}
      </div>
    </div>
  );
}
