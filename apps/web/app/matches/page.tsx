import { redirect } from "next/navigation";

// Matches now lives inside Applications; old links (Today's tiles, bookmarks) still work.
export default function MatchesRedirect() {
  redirect("/applications/matches");
}
