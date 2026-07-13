import { useEffect, useState } from "react";

export interface Clock {
  time: string; // 10:42 PM
  date: string; // May 19, 2025 | Monday
  greeting: string; // Good Evening
}

function format(now: Date): Clock {
  const time = now.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
  const date = now.toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
  });
  const weekday = now.toLocaleDateString("en-US", { weekday: "long" });
  const h = now.getHours();
  const greeting = h < 12 ? "Good Morning" : h < 17 ? "Good Afternoon" : "Good Evening";
  return { time, date: date + "  |  " + weekday, greeting };
}

export function useClock(): Clock {
  const [clock, setClock] = useState<Clock>(() => format(new Date()));
  useEffect(() => {
    const id = setInterval(() => setClock(format(new Date())), 1000);
    return () => clearInterval(id);
  }, []);
  return clock;
}
