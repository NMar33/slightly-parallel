/*
 * The top of the task window: the title row (New/Edit task, the id, the
 * release button, the gear, close) and the gear's preferences panel —
 * window size, description box, axes, ▶ mode, sections, new-task defaults.
 * Moved out of TaskEditor.tsx; the window owns the prefs and passes them.
 */

import { Settings2 } from 'lucide-react'
import { IconButton } from '../../../../components/primitives'
import { PrefChip, PrefRow } from '../../../../components/Prefs'
import { ReleaseButton } from '../ReleasePrompt'
import { AXES, MODAL_SECTIONS } from '../model'
import type { ChainMode, ModalDescSize, ModalPrefs, ModalWidth, TaskRow } from '../model'
import { t } from '../../../../i18n/scope/project'

export function EditorHeader({ isEdit, existingTask, onRelease, tuning, setTuning, onClose }: {
  isEdit: boolean
  existingTask?: TaskRow | null
  onRelease?: (task: TaskRow) => void
  tuning: boolean
  setTuning: (fn: (v: boolean) => boolean) => void
  onClose: () => void
}) {
  return (
    <div className="flex items-baseline gap-8">
      <span id="task-modal-title" className="text-16 font-semibold text-primary">
        {isEdit ? t('Edit task') : t('New task')}
      </span>
      {isEdit && existingTask && (
        <span className="text-11 text-tertiary font-mono">
          {existingTask.id}
        </span>
      )}
      {isEdit && existingTask && (
        <ReleaseButton task={existingTask} size={20} className="ml-auto"
          onOpen={onRelease ? () => onRelease(existingTask) : undefined} />
      )}
      <IconButton
        size={20}
        label={t('Window settings: size, sections, defaults for new tasks')}
        onClick={() => setTuning((v) => !v)}
        aria-label={t('Window settings')}
        aria-expanded={tuning}
        active={tuning}
        className={isEdit && existingTask ? '' : 'ml-auto'}
      >
        <Settings2 size={13} aria-hidden />
      </IconButton>
      <IconButton label={t('Close')} onClick={onClose} className="text-16">×</IconButton>
    </div>
  )
}

export function WindowPrefs({ prefs, applyPrefs }: { prefs: ModalPrefs; applyPrefs: (next: ModalPrefs) => void }) {
  return (
      <div className="rounded-input border border-border-subtle bg-elevated px-10 py-8 flex flex-wrap items-center gap-x-16 gap-y-6">
        <PrefRow label={t('Window')}>
          {(['compact', 'normal', 'wide'] as ModalWidth[]).map((w) => (
            <PrefChip
              key={w}
              on={prefs.width === w}
              onClick={() => applyPrefs({ ...prefs, width: w })}
            >
              {w}
            </PrefChip>
          ))}
        </PrefRow>
        <PrefRow label={t('Description box')}>
          {(['s', 'm', 'l'] as ModalDescSize[]).map((d) => (
            <PrefChip
              key={d}
              on={prefs.desc === d}
              onClick={() => applyPrefs({ ...prefs, desc: d })}
            >
              {d.toUpperCase()}
            </PrefChip>
          ))}
        </PrefRow>
        <PrefRow label={t('Axes')}>
          {AXES.map((a) => (
            <PrefChip
              key={a}
              on={prefs.axes[a]}
              onClick={() => applyPrefs({ ...prefs, axes: { ...prefs.axes, [a]: !prefs.axes[a] } })}
            >
              {a}
            </PrefChip>
          ))}
        </PrefRow>
        <PrefRow label={t('▶ after save')}>
          {([['next', t('next only')], ['group', t('next + group')]] as Array<[ChainMode, string]>).map(([m, label]) => (
            <PrefChip
              key={m}
              on={prefs.chain === m}
              onClick={() => applyPrefs({ ...prefs, chain: m })}
            >
              {label}
            </PrefChip>
          ))}
        </PrefRow>
        <PrefRow label={t('Sections')}>
          {MODAL_SECTIONS.map((sec) => (
            <PrefChip
              key={sec}
              on={prefs.sections[sec]}
              onClick={() => applyPrefs({ ...prefs, sections: { ...prefs.sections, [sec]: !prefs.sections[sec] } })}
            >
              {sec}
            </PrefChip>
          ))}
        </PrefRow>
        <PrefRow label={t('New tasks start with')}>
          <PrefChip on={prefs.autoNew} onClick={() => applyPrefs({ ...prefs, autoNew: !prefs.autoNew })}>
            {t('auto')}
          </PrefChip>
          <PrefChip on={prefs.evidenceNew} onClick={() => applyPrefs({ ...prefs, evidenceNew: !prefs.evidenceNew })}>
            {t('evidence')}
          </PrefChip>
        </PrefRow>
        <span className="text-10 text-tertiary font-mono ml-auto">
          {t('remembered for every task · ▶ saves and opens the next one, keeping sprint, lane and column')}
        </span>
      </div>
  )
}
