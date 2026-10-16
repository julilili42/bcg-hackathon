import { useEvents, useFocus } from "./api";
import WaterMap from "./WaterMap";

export default function MapPage() {
  const data = useEvents(2000);
  const focus = useFocus(data);
  return <WaterMap waterpoints={data.waterpoints} villages={data.villages} hazards={data.hazards} focus={focus} legend />;
}
