import type { Skill } from './types';
import type { MouseEvent } from 'react';
import { OFFICIAL_STORE_INDEX_URL } from '../../data/store';

export const STORE_INDEX_URL = OFFICIAL_STORE_INDEX_URL;
export const TTL_BASE = STORE_INDEX_URL.replace('index.json', 'packages/');

export function normSkill(pkg: any, skill: any): Skill {
  const qid = `${pkg.package_id}/${skill.id}`;
  const parts = qid.split('/');
  return {
    packageId: pkg.package_id,
    skillId: skill.id,
    qualifiedId: qid,
    description: skill.description || pkg.description || '',
    aliases: Array.isArray(skill.aliases) ? skill.aliases : [],
    trustTier: pkg.trust_tier || 'verified',
    installCommand: `npx ontoskills install ${qid}`,
    author: parts[0] || '',
    category: skill.category || '',
    intents: Array.isArray(skill.intents) ? skill.intents : [],
    dependsOn: Array.isArray(skill.depends_on_skills) ? skill.depends_on_skills : [],
    version: pkg.version || '',
    modules: Array.isArray(pkg.modules) ? pkg.modules : [],
  };
}

export function hashStr(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

export function navClick(href: string, navigate: (href: string) => void) {
  return (e: MouseEvent) => {
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    navigate(href);
  };
}
