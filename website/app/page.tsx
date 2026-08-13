import { Hero } from "@/components/hero";
import { PipelineStrip } from "@/components/pipeline-strip";
import { Audiences } from "@/components/audiences";
import { Features } from "@/components/features";
import { NoteStyles } from "@/components/note-styles";
import { PrivacySection } from "@/components/privacy-section";
import { Pricing } from "@/components/pricing";
import { Requirements } from "@/components/requirements";
import { Faq } from "@/components/faq";
import { ClosingCta } from "@/components/closing-cta";

export default function HomePage()
{
  return (
    <>
      <Hero />
      <PipelineStrip />
      <Audiences />
      <Features />
      <NoteStyles />
      <PrivacySection />
      <Pricing />
      <Requirements />
      <Faq />
      <ClosingCta />
    </>
  );
}
