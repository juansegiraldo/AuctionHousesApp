import { Navigation } from "@/components/Navigation";
import { HomeContent } from "@/components/HomeContent";

export default function Home() {
  return (
    <div className="min-h-screen bg-gray-50">
      <Navigation />
      <HomeContent />
    </div>
  );
}
