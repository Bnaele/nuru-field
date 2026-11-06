// FieldPage — everything about the field: conditions, location picker, crops,
// market prices, and the plants being tracked.
//
// The plants list is loaded once here and handed to both cards. Previously each
// card kept its own copy in localStorage, so a plant added in one never appeared
// in the other until a remount.

import FieldDashboard from '../components/FieldDashboard'
import FieldMap from '../components/FieldMap'
import CropRecommendations from '../components/CropRecommendations'
import MarketSnapshot from '../components/MarketSnapshot'
import MyPlants from '../components/MyPlants'
import WateringReminders from '../components/WateringReminders'
import { usePlants } from '../hooks/usePlants'

export default function FieldPage({
  fieldProfile,
  locationStatus,
  locationTone,
  locationLoading,
  onUseMyLocation,
  onMapPick,
}) {
  // /field only renders for a signed-in session, so the plant list is always
  // available here.
  const plants = usePlants()

  return (
    <main>
      <FieldDashboard
        fieldProfile={fieldProfile}
        locationStatus={locationStatus}
        locationTone={locationTone}
        locationLoading={locationLoading}
        onUseMyLocation={onUseMyLocation}
      />
      <FieldMap onPick={onMapPick} />
      <CropRecommendations fieldProfile={fieldProfile} />
      <MarketSnapshot />
      <MyPlants plants={plants} />
      <WateringReminders plants={plants} />
    </main>
  )
}
