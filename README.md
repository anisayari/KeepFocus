# Gaze Focus TamTam

Petit outil macOS qui surveille ton regard avec la webcam:

- si tu regardes l'ecran, la video se met en pause ;
- si tu detournes le regard, la video se lance tout de suite avec le son ;
- la calibration peut parler sur Mac pour te dire quand changer de cible.

## Lancer sur Mac

Double-clique sur [run_mac.command](/Users/anisayari/Desktop/projects/gaze-focus-tamtam/run_mac.command) ou lance:

```bash
./run_mac.command
```

Le script:

- cree `.venv` si besoin ;
- installe les dependances ;
- ouvre la webcam en grand ;
- charge la video locale ;
- te propose une calibration au demarrage.

## Raccourcis

- `C` au demarrage: lancer une calibration
- `S` / `Entree` / `Espace`: continuer avec la calibration sauvee ou sans calibration
- `C` pendant le suivi: recalibrer
- `Q` ou `ESC`: quitter

## Fichiers utiles

- [main.py](/Users/anisayari/Desktop/projects/gaze-focus-tamtam/main.py): logique webcam, detection du regard, calibration, player
- [video_player.html](/Users/anisayari/Desktop/projects/gaze-focus-tamtam/video_player.html): fenetre video
- [videos/youtube_trigger_video.mp4](/Users/anisayari/Desktop/projects/gaze-focus-tamtam/videos/youtube_trigger_video.mp4): clip joue quand tu regardes ailleurs
- [models/face_landmarker.task](/Users/anisayari/Desktop/projects/gaze-focus-tamtam/models/face_landmarker.task): modele MediaPipe

## Notes

- Chrome est prefere sur Mac pour le player.
- Le profil de calibration est sauve dans `attention_calibration.json`.
- La fenetre video reste synchronisee en play/pause selon ton regard.
