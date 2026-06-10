import { TickerDetailPage } from "@/components/wtaf/pages/watchlist";

export default async function TickerDetail({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker } = await params;
  return <TickerDetailPage ticker={decodeURIComponent(ticker)} />;
}
