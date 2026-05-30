# Arranger

**Arranger** is an automation bridge for **Radarr** and **Sonarr** that uses API rules to organize media into the correct root folders based on metadata such as genre, while protecting TV shows from being moved before they are safe to move.

## Purpose

Arranger is built to solve one main problem:

> If a movie or show belongs in a special folder like Kids, Family, Anime, or General, Arranger can detect that through Radarr/Sonarr metadata and automatically move it using the correct Arr API.

This avoids manually checking items, mass-editing root folders, or moving files outside Radarr/Sonarr.

## Core Features

- Uses the **Radarr API** for movie organization.
- Uses the **Sonarr API** for TV show organization.
- Reads metadata such as:
  - Genres
  - Tags
  - Root folder
  - Current path
  - Monitored status
  - Download/import status
- Moves items only through the Arr API.
- Supports genre-based folder rules.
- Includes safety checks to avoid breaking active downloads or incomplete shows.
- Supports dry-run mode before making real changes.
- Logs every decision.

## Example Use Case

A movie is added to Radarr:

```text
Movie: Finding Nemo
Genres: Animation, Family, Adventure
Current Path: /media/movies/general/Finding Nemo (2003)
Correct Path: /media/movies/kids/Finding Nemo (2003)
