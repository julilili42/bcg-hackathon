import { useEvents } from "./api";
import WaterMap from "./WaterMap";

export default function MapPage() {
  const { waterpoints } = useEvents(5000);
  return <WaterMap waterpoints={waterpoints} legend />;
}
