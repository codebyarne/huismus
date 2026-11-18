// SPDX-FileCopyrightText: 2026 Huismus contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
import { Composition } from "remotion";
import { Bonnetjes, DURATION as BONNETJES } from "./Bonnetjes";
import { Overzicht, DURATION as OVERZICHT } from "./Overzicht";

export const Root = () => (
  <>
    <Composition id="bonnetjes" component={Bonnetjes} durationInFrames={BONNETJES} fps={30} width={1920} height={1080} />
    <Composition
      id="overzicht"
      component={Overzicht}
      durationInFrames={OVERZICHT}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={{ stem: true, ondertitels: false }}
    />
  </>
);
