# Artifact v2

Artifact v2 is the current bounded pilot source after one repair. The source
change rejects whitespace-only identifiers with `value.strip()` and preserves
the existing header validation behavior. The repair also added a focused
regression test. The final source material digest used in the verifier handoff
is `sha256:a740e844f98d7fdcd686f119cb1f1f4b80f21c92a4e524edaa27591dfcf73a8a`.

The verifier's fresh evidence observation is recorded as v3 because the final
test/evidence packet was rebound after the repair; this is an evidence revision,
not a second code repair. The verifier remained read-only and did not write the
pilot.
