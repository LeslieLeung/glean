import { useTranslation } from '@glean/i18n'
import { PreferenceTab } from '../components/tabs/PreferenceTab'

export default function PreferencePage() {
  const { t } = useTranslation('settings')
  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-6 sm:px-6">
      <h1 className="text-foreground text-xl font-semibold">{t('preferences.title')}</h1>
      <PreferenceTab />
    </div>
  )
}
