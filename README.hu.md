# CB1 PlayerProcessInfo (service.cb1.ppi)

Szerkeszthető, testreszabható másolat a
[CroqueMr/libreelec-x86-DV](https://github.com/CroqueMr/libreelec-x86-DV) LibreELEC-build **cb1
PlayerProcessInfo paneljéről**, plusz egy opcionális, főleg olvasó webszerver egy kompatibilis mobil apphoz.
Magyar és angol felület.

*English: [README.md](README.md)*

> Nem áll kapcsolatban a LibreELEC, Kodi, CroqueMr vagy TinyPPI projektekkel, és nem is támogatják.
> A „TinyPPI Mobile" nevet csak a kompatibilitás jelzésére használjuk. A Dolby, Dolby Vision és más
> formátumnevek a tulajdonosaik védjegyei.

> **Megjegyzés:** a panel sablon (`template/cb1/`) egyelőre nem része a tárolónak, így az addon csak keretrendszer; a panelfájlok akkor kerülnek be, ha az upstream projekttel a licenc kérdése tisztázódik.

## Működés
- `template/cb1/*.xml` a **szerkeszthető forrás** (a színek `@@token@@` helyőrzők; a feliratok magyarul vannak megírva, angolra a generáláskor fordítja a `strings_en.py`).
- Indításkor, és minden beállítás-változáskor a service legenerálja a `media/cb1/*.xml` fájlokat a template-ből.
- A `media/` elemeit `mount --bind` köti a `/usr/share/kodi/media`-ra; az addon leállításakor (letiltás, kilépés) leválik.
- A `media/cb1/` fájlokat **ne szerkeszd közvetlenül**, felülíródnak. A `cb1-*.png` textúrák viszont közvetlenül cserélhetők.
- Template szerkesztése után: Beállítások → Haladó → „Panel újragenerálása most".
- **Csak LibreELEC x86 + a CroqueMr Dolby Vision build** (a Kodi rootként fut; kell hozzá a `cb1` panel és a `DV.*` ablak-property-k).

## Beállítások
- **Hátterek:** főpanel, alsó (mérő) kártya, lejátszási módok panel: szín + átlátszatlanság; kijelölt sor színe.
- **Szövegszínek:** fő szöveg, értékek, címkék, kiemelés (zöld), figyelmeztetés (sárga), valamint külön az oszlopcímek, oszlopfejlécek, szakaszcímek és értékek színe.
- **Haladó:** nyelv (Automatikus / Angol / Magyar), egyéni hex szín (RRGGBB vagy AARRGGBB), skin újratöltése, újragenerálás, DV adatok frissítése lejátszás-indításkor.
- **Mobil app:** opcionális webszerver (alapból ki), port, token, vezérlés/filmtár kapcsoló, opcionális MDBList API-kulcs.

## Infolabelek skinhez
A fork a `playerprocessinfo` ablakra tölti a `DV.*` property-ket:

    $INFO[Window(playerprocessinfo).Property(DV.L1PQ)]

<details>
<summary>A DV.* property-k listája (86)</summary>

- `DV.AIL1`
- `DV.AIL3`
- `DV.AIModel`
- `DV.AdmissionReason`
- `DV.AppliedBlocks`
- `DV.AtomicResult`
- `DV.BL`
- `DV.BeforeAI`
- `DV.CLL`
- `DV.CM`
- `DV.CPU`
- `DV.Circuit`
- `DV.Committed`
- `DV.CreativeTrims`
- `DV.DecodedHLG`
- `DV.Display`
- `DV.DisplayBlack`
- `DV.DroppedSkipped`
- `DV.EL`
- `DV.Engine`
- `DV.Enhanced`
- `DV.FEL`
- `DV.FELUpscaling`
- `DV.Fallback`
- `DV.GPUAvailable`
- `DV.GPURender`
- `DV.HDR10PlusAverage`
- `DV.HDR10PlusCurve`
- `DV.HDR10PlusMaxSCL`
- `DV.HDR10PlusSaturation`
- `DV.HDR10PlusSection`
- `DV.HDR10PlusTarget`
- `DV.HDR10Target`
- `DV.HDR10TargetLabel`
- `DV.HDR10TargetOrigin`
- `DV.L10`
- `DV.L11`
- `DV.L1Nits`
- `DV.L1PQ`
- `DV.L254`
- `DV.L255`
- `DV.L3`
- `DV.L4`
- `DV.L5`
- `DV.L9`
- `DV.Layers`
- `DV.Level`
- `DV.Mastering`
- `DV.Memory`
- `DV.MinimumLinkBits`
- `DV.Mode`
- `DV.OutputL1`
- `DV.OutputL2Targets`
- `DV.OutputL8Targets`
- `DV.OutputStage`
- `DV.ParsedBlocks`
- `DV.Precision`
- `DV.ProcessingVisible`
- `DV.Profile`
- `DV.ProfileDetail`
- `DV.RPU`
- `DV.Reconstruction`
- `DV.ReferenceWarning`
- `DV.RequestedPolicy`
- `DV.SignalIntent`
- `DV.SourceBits`
- `DV.SourceColour`
- `DV.SourceLight`
- `DV.SourceMastering`
- `DV.SourcePixelFormat`
- `DV.TVProfile`
- `DV.TransmittedBlocks`
- `DV.Transport`
- `DV.UsedHDR10PlusAverage`
- `DV.UsedHDR10PlusAvg`
- `DV.UsedHDR10PlusMax`
- `DV.UsedHDR10PlusMaxRGB`
- `DV.UsedHDRCLL`
- `DV.UsedHDRMax`
- `DV.UsedHDRMin`
- `DV.UsedHDRStatic`
- `DV.UsedL1Nits`
- `DV.UsedL1PQ`
- `DV.UsedL3`
- `DV.UsedL6Max`
- `DV.Version`
</details>

## Mobil app (TinyPPI Mobile kompatibilis)
A beállítások → **Mobil app** alatt bekapcsolható egy webszerver (alapból ki), amely a TinyPPI Mobile
app nyilvános HTTP/JSON felületét valósítja meg ([CE-Repo/tinyppi-mobile](https://github.com/CE-Repo/tinyppi-mobile), MIT).
Független megvalósítás (a TinyPPI addon kódját, nevét, grafikáját nem használja).
Van benne: élő panel, borító/háttér, lejátszásvezérlés, filmtár, sorozatok, folytatás, részletek.
Nincs: VS10 módváltás, eseménynapló/grafikon, színészportrék. A vezérlés és a filmtár egy kapcsolóval
letiltható (a token ekkor is kell az olvasáshoz). Forrás: `web.py`, `media.py`.

**Több értékelés:** ingyenes [MDBList](https://mdblist.com) API-kulcs (mdblist.com → Preferences) a Mobil app beállításnál.
Az addon azonosító (IMDb/TMDb) alapján kéri le, és a profilban (`addon_data/service.cb1.ppi/mdblist.json`)
7 napig tárolja. A TMDb Helper értékei a lejátszott filmnél továbbra is bekerülnek.
Az MDBList API használatára az MDBList saját feltételei vonatkoznak; kulcs nincs a csomagban.

## Licenc
GPL-2.0-or-later, lásd `LICENSE` és `NOTICE.txt` (harmadik féltől származó és származtatott anyagok).
