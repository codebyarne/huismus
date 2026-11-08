// SPDX-FileCopyrightText: 2026 Huismus contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
import { Composition } from "remotion";
import { Bonnetjes, DURATION } from "./Bonnetjes";

export const Root = () => (
  <Composition
    id="bonnetjes"
    component={Bonnetjes}
    durationInFrames={DURATION}
    fps={30}
    width={1920}
    height={1080}
  />
);
