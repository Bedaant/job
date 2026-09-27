"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/auth";

// "/" only routes: signed in -> Today, otherwise -> sign in.
export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace(getToken() ? "/today" : "/login");
  }, [router]);
  return null;
}
