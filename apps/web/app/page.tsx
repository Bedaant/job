"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/auth";

// "/" used to be the pre-pivot single-user MVP dashboard (pages/index.js). It
// now only routes: signed in -> the review queue, otherwise -> sign in.
export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace(getToken() ? "/review" : "/login");
  }, [router]);
  return null;
}
