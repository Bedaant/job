"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, type Campaign, type CampaignStatus } from "@/lib/api";

/** Pause / resume / start a campaign. Optimistic: the status flips the moment it
 * is pressed via the ["campaigns"] cache; a failed PATCH puts the old status back
 * and `error` says so. No confirm — pausing is safe and reversible. */
export function useCampaignStatus(campaign: Campaign | undefined) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (next: CampaignStatus) => api.updateCampaign(campaign!.id, { status: next }),
    onMutate: (next) => {
      setError(null);
      const previous = queryClient.getQueryData<Campaign[]>(["campaigns"]);
      queryClient.setQueryData<Campaign[]>(["campaigns"], (old) =>
        old?.map((c) => (c.id === campaign!.id ? { ...c, status: next } : c))
      );
      return { previous };
    },
    onError: (err, _next, ctx) => {
      queryClient.setQueryData(["campaigns"], ctx?.previous);
      const why = err instanceof ApiError ? err.message : "Something went wrong. Try again.";
      setError(`Couldn't change the campaign: ${why} Its status has not changed.`);
    },
    onSuccess: (saved) => {
      queryClient.setQueryData<Campaign[]>(["campaigns"], (old) => old?.map((c) => (c.id === saved.id ? saved : c)));
    },
  });

  return { setStatus: mutation.mutate, pending: mutation.isPending, error };
}
