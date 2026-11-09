import { ArrowRight } from "lucide-react";
import { Link } from "react-router";

export default function NotFoundPage() {
  return (
    <div className="grid min-h-[50vh] place-items-center text-center">
      <div>
        <p className="text-8xl font-extrabold text-lime [font-stretch:120%] [text-shadow:0_6px_0_#4d7c0f]">404</p>
        <h1 className="mt-4 text-3xl font-extrabold">This page drifted out to sea</h1>
        <p className="mt-2 text-muted-foreground">The address does not match any page of the desk.</p>
        <Link to="/" className="lime-key mt-6 inline-flex h-11 items-center gap-2 rounded-full px-5 font-bold">Back to home <ArrowRight className="size-4" /></Link>
      </div>
    </div>
  );
}
