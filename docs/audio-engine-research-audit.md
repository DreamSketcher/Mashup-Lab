# Предпроектный аудит аудиодвижка

Дата: 2026-11-08. Статус: исследование для согласования; **не утверждённый
контракт и не решение о включении зависимостей**. См. также
[конкретные рекомендации](audio-engine-architecture-recommendations.md).

## Краткий вывод и стоп-пункт

Обновление после решения владельца: для MVP выбраны независимые клипы (A),
ручной constant-tempo sync и сохранение sample-peak policy; LUFS и анализ
отложены. Лицензия проекта и точные правила границ ещё требуют согласования.
См. [обновлённые рекомендации](audio-engine-architecture-recommendations.md).

В проекте уже есть небольшой экспериментальный WAV-рендерер; это **не** полный
аудиодвижок. Критическое для дальнейшего DSP решение пока не определено:
**границы клипа, контекст фильтров и начальная фаза resampler при независимой
обработке соседних интервалов**. Текущий контракт предписывает сначала вырезать
интервал, затем ресемплировать; он не обещает эквивалентность единой обработке
соседних отрезков. Эксперимент ниже показывает реальную разницу у границы даже
при одинаковой суммарной длине. Если позднее требовать бесшовного непрерывного
результата, придётся определить контекст, задержку, абсолютную координату и
правила склейки **до** реализации адаптера. Вариант A выбран; конкретную
семантику padding/reset/phase ещё нужно проверить и согласовать, прежде чем
расширять DSP. Действующую спецификацию в этом
аудите не меняем.

Решения-кандидаты: для ресемплинга исследовать libsoxr и libsamplerate; для
независимого time/pitch — Rubber Band, SoundTouch и Signalsmith Stretch; для
анализа — опциональный librosa; для LUFS/true peak — libebur128. Ни одна
библиотека не выбрана окончательно. Сначала — юридическая проверка лицензий,
испытания в Windows и на музыкальных примерах. В частности, в репозитории
Mashup Lab на проверенном коммите нет корневого файла LICENSE и метаданных
лицензии в `pyproject.toml`: коммерческую/свободную совместимость нельзя
предполагать. Авторские права и лицензии самих аудиофайлов — отдельный вопрос.

## Метод и границы доказательств

Проверены дерево и выбранные исходники/тесты по зафиксированным GitHub-ревизиям
ниже; ревизия — не рекомендация использовать именно этот unreleased build.
Ссылки на код по возможности закреплены по SHA. Размер исследования — аудит
точек интеграции, **не** полный аудит каждого проекта или всех его тестов.
Указание теста означает, что он существует и просмотрен, а не что он запущен
или доказывает музыкальное качество. Фактически выполнен только описанный ниже
локальный эксперимент libsoxr. Не было сравнительных аудио-прослушиваний,
Windows-сборок внешних проектов, изучения всех issues, профилирования или
юридической экспертизы. Windows в таблице означает наличие upstream-поддержки
или исходников для неё, а не проверку конкретной DLL/wheel. Лицензия сборки
может отличаться от лицензии основного исходного файла и включать зависимости.
Стоимость — качественная оценка без сравнимых замеров на целевом ПК.

## Актуальность и воспроизводимость обзора

Срез дерева по SHA в ссылках выше/ниже позволяет повторить чтение, но не
означает, что это последний стабильный выпуск. По GitHub `releases/latest` на
момент исследования обнаружены: librosa 1.0.0 (2026-08), soundfile 0.14.0
(2026-06), libsamplerate 0.2.2 (2021-09), libsndfile 1.2.2 (2023-08),
libebur128 1.2.6 (2021-02), pyloudnorm 0.2.0 (2026-01), Mixxx 2.5.6
(2026-03), Audacity 4.0.2 (2026-11), JUCE 9.0.5 (2026-11), Pedalboard 0.9.26
(2026-10), Wavelength 0.6.0 (2026-10), Produzre 0.10.0 (2026-09).
Для Essentia GitHub latest показал 2.0.1 (2014); это **не** надёжный критерий
актуального поддерживаемого канала проекта — отдельно уточнить используемый
release/wheel. Для Rubber Band, soxr, Signalsmith и FFmpeg запрос GitHub latest
не вернул release; это не означает, что выпусков у upstream нет. SoundTouch
исследован по зеркалу версии 2.3.1, не как подтверждение последней версии.
Старый release не доказывает заброшенность; новый коммит не доказывает
поддержку, качество или безопасность. Открытые bugs/CVEs и поддержку выбранных
пакетов нужно перепроверить при квалификации; здесь полный issue-review не
проводился.

## Сравнение готовых компонентов

| Решение | Что действительно изучено / интеграция | Лицензия и Windows | Качество, цена, пригодность и пробел тестирования |
|---|---|---|---|
| **libsndfile + python-soundfile + NumPy** | Уже применяются: [`render.py`](../mashup/render.py) читает WAV через soundfile из проверенных байтов, NumPy сводит, Python `wave` записывает явно квантованный PCM. [soundfile код](https://github.com/bastibe/python-soundfile/blob/e8293394e6b7/soundfile.py), [libsndfile WAV](https://github.com/libsndfile/libsndfile/blob/396a715daeae/src/wav.c), [тест PCM](https://github.com/libsndfile/libsndfile/blob/396a715daeae/tests/pcm_test.tpl). | soundfile BSD-3-Clause, libsndfile LGPL-2.1-or-later; NumPy BSD-3-Clause. Windows wheels существуют; состав DLL проверить для конкретного wheel. | Оставить для текущего узкого среза; декодер не отвечает за музыкальное выравнивание. Память O(все источники + весь микс), не подходит для длинных проектов без изменения модели. Ограничения WAV/extensible проверять отдельно. |
| **libsoxr / python-soxr** | C API [`soxr.h`](https://github.com/chirlu/soxr/blob/945b592b7047/src/soxr.h), потоковый процесс, delay и quality presets; [примеры и тесты](https://github.com/chirlu/soxr/blob/945b592b7047/tests/CMakeLists.txt); [Python binding](https://github.com/dofuuz/python-soxr). | libsoxr LGPL-2.1-or-later; отдельно проверить лицензию Python binding и бинарный пакет. Windows wheels Python binding заявлены upstream; в этом аудите не проверены. | Первый кандидат на offline SRC; качество зависит от preset, фазы и фильтра. Стоимость зависит от коэффициента, режима, каналов и блоков. Эксперимент — ниже; он не доказывает отсутствие aliasing или превосходство над другими. Основное зеркало кода в этом срезе старое; точную активную поставку и CVE проверить до pin. |
| **libsamplerate** | [`src_process`](https://github.com/libsndfile/libsamplerate/blob/0844c208f683/src/samplerate.c) сообщает consumed/generated frames; [downsample test](https://github.com/libsndfile/libsamplerate/blob/0844c208f683/tests/downsample_test.c) и другие тесты в дереве. | BSD-2-Clause в текущей версии; [Win32](https://github.com/libsndfile/libsamplerate/tree/0844c208f683/Win32) build-файлы. Лицензию выбранного Python wrapper проверить отдельно. | Альтернатива SRC с sinc-режимами; стоимость/задержка зависят от converter, соотношения частот и размера окна. Сравнить aliasing, концы, length и CPU на одной выборке; локально не измерен. |
| **Rubber Band** | [Stretcher API](https://github.com/breakfastquay/rubberband/blob/e4296ac80b11/rubberband/RubberBandStretcher.h): offline `study` → `process` → `retrieve`, фиксированные ratio; отдельные варианты режимов, start pad/delay, многоканальность. [R2/R3 dispatcher](https://github.com/breakfastquay/rubberband/blob/e4296ac80b11/src/RubberBandStretcher.cpp); [sinusoid и length tests](https://github.com/breakfastquay/rubberband/blob/e4296ac80b11/src/test/TestStretcher.cpp). | GPL-2.0-or-later **или** отдельная коммерческая лицензия; зависимости/сборка имеют собственные условия. Есть Windows-пути сборки; конкретный пакет не проверен. | Сильный кандидат для offline музыкального растяжения и pitch, но сложен и CPU-intensive; R2/R3 и режимы не взаимозаменяемы. Заявленные offline exact start/duration не равны гарантии sample-exact положения любого транзиента. Требуются собственные listening/latency/ratio/stereo tests. |
| **SoundTouch** | [`SoundTouch.cpp`](https://github.com/AstaTus/soundtouch/blob/16e1b7ebc355/source/SoundTouch/SoundTouch.cpp): tempo через TDStretch, pitch как комбинация tempo и rate, FIFO `putSamples`/`receiveSamples`, буферная задержка; [Windows smoke script](https://github.com/AstaTus/soundtouch/blob/16e1b7ebc355/bin/run_test.cmd). | LGPL-2.1, имеются Windows project/DLL; это GitHub-зеркало, не подтверждение актуального релиза официального upstream. Проверить binding и точную лицензию поставки. | Альтернатива time-domain; FIFO, flush, реальная длина и потокобезопасность параметров требуют адаптации. Заявленное качество и CPU на наших файлах не сравнивались; отсутствие тут просмотренных golden vectors не значит, что их нигде нет. |
| **Signalsmith Stretch** | [C++ реализация](https://github.com/Signalsmith-Audio/signalsmith-stretch/blob/88061fd4eda5/signalsmith-stretch.h), [API/readme](https://github.com/Signalsmith-Audio/signalsmith-stretch/blob/88061fd4eda5/README.md): input/output latency, pitch и процесс по блокам. | MIT; C++ переносим, Windows/MSVC в нашем окружении не собран. Дополнительные заголовки/зависимости и binding лицензировать отдельно. | Перспективная permissive альтернатива для отдельной квалификации, не готовый Python drop-in. В просмотренном дереве не обнаружен комплект upstream unit/golden tests; качество, flush и адаптер не проверены. |
| **FFmpeg** | [amix](https://github.com/FFmpeg/FFmpeg/blob/b2b543c07924/libavfilter/af_amix.c), [atempo](https://github.com/FFmpeg/FFmpeg/blob/b2b543c07924/libavfilter/af_atempo.c), [loudnorm](https://github.com/FFmpeg/FFmpeg/blob/b2b543c07924/libavfilter/af_loudnorm.c), [rubberband adapter](https://github.com/FFmpeg/FFmpeg/blob/b2b543c07924/libavfilter/af_rubberband.c); [FATE audio](https://github.com/FFmpeg/FFmpeg/blob/b2b543c07924/tests/fate/filter-audio.mak). | Базовый состав в основном LGPL-2.1+, опции GPL и внешние библиотеки меняют обязательства; см. [LICENSE](https://github.com/FFmpeg/FFmpeg/blob/b2b543c07924/LICENSE.md). Windows сборки есть; проверить configure каждого бинарника. | Готовый инструмент конвертации/референс для фильтров, но не эквивалент нашему контракту по умолчанию: в коде `amix` `normalize=1`. Таймстемпы, sample formats, resampling, фильтры и фактический порядок должны быть явно зафиксированы. Стоимость зависит от pipeline; не подменять им рендерер без тестов. |
| **SciPy signal correlation** | [`signal.correlate` и `correlation_lags`](https://github.com/scipy/scipy/blob/1f1abc33088f/scipy/signal/_signaltools.py); [тесты correlate/lags](https://github.com/scipy/scipy/blob/1f1abc33088f/scipy/signal/tests/test_signaltools.py). Поддерживает direct и FFT, но не является готовым музыкальным sync или GCC-PHAT. | SciPy BSD-3-Clause; Windows wheels поддерживаются в зависимости от Python/архитектуры; не установлены здесь. Direct для двух длиной N — O(N²), FFT примерно O(N log N) и O(N) памяти; ограничение лагов может изменить стоимость. Пиковый лаг пригоден лишь для похожих сигналов, ложные пики/тишина требуют отказа или ручной проверки. |
| **libebur128 / pyloudnorm** | [libebur128 реализация](https://github.com/jiixyj/libebur128/blob/67b33abe1558/ebur128/ebur128.c), [tests](https://github.com/jiixyj/libebur128/blob/67b33abe1558/test/tests.c); [pyloudnorm meter](https://github.com/csteinmetz1/pyloudnorm/blob/b8d67bfd3ce5/pyloudnorm/meter.py) и [тесты с 1770-2 WAV](https://github.com/csteinmetz1/pyloudnorm/blob/b8d67bfd3ce5/tests/test_loudness.py). | Оба MIT; Windows C/Python интеграция зависит от сборки и зависимостей, не проверена. | Кандидаты для последующей **метрики**, не для автоматической смены gain. libebur128 включает true peak, pyloudnorm рассматриваем как интегральный loudness reference, не приписываем ему true peak без проверки. Молчание/короткие файлы и gating требуют явного статуса. Исторические 1770-2 тесты не доказывают соответствие новейшей редакции. |
| **Pedalboard / JUCE dynamics** | [Compressor wrapper](https://github.com/spotify/pedalboard/blob/master/pedalboard/plugins/Compressor.h) вызывает JUCE с threshold/ratio/attack/release; [1](https://github.com/spotify/pedalboard). | Pedalboard GPL-3.0, Windows wheels заявлены; состав включает JUCE и др. зависимости. | Кандидат на отдельное исследование компрессора/лимитера позднее, не реализация текущего sample-peak policy. Stateful, добавляет параметры, возможную задержку и хвост; CPU пропорционален числу обрабатываемых сэмплов/полос, фактический CPU не измерен. Тесты и конкретный release не квалифицированы. |

### Полезные музыкальные анализаторы: отдельно от исполнения

| Решение | Реальные точки | Лицензия/Windows, цена и предел |
|---|---|---|
| **librosa** | [beat.py](https://github.com/librosa/librosa/blob/1beafa2c7c99/librosa/beat.py), [DTW](https://github.com/librosa/librosa/blob/1beafa2c7c99/librosa/sequence.py), [segment.py](https://github.com/librosa/librosa/blob/1beafa2c7c99/librosa/segment.py), [beat tests](https://github.com/librosa/librosa/blob/1beafa2c7c99/tests/test_beat.py) и [sequence tests](https://github.com/librosa/librosa/blob/1beafa2c7c99/tests/test_sequence.py). Feature/chroma/MFCC — признаки, не готовая истина о тональности/гармонии. DTW поддерживает constraint и subsequence. | ISC; Windows зависит от совместимости Python/Numba/SciPy wheels, не тестировали. Beat/tempo — оценки, половинный/двойной BPM возможен; beat не означает downbeat или размер. DTW O(NM) времени/памяти для полной cost matrix, не подходит наивно для часов записи; features/hop/ограничения меняют результат. [код `load`](https://github.com/librosa/librosa/blob/1beafa2c7c99/librosa/core/audio.py) показывает, что `load` по умолчанию изменяет частоту/моно — для воспроизводимого анализа явно задавать параметры. |
| **Essentia** | [RhythmExtractor2013](https://github.com/MTG/essentia/blob/23ae7baddecf/src/algorithms/rhythm/rhythmextractor2013.cpp) возвращает beats/BPM и confidence, но в коде confidence для `degara` не информативна; [KeyExtractor](https://github.com/MTG/essentia/blob/23ae7baddecf/src/algorithms/extractor/keyextractor.cpp); [rhythm tests](https://github.com/MTG/essentia/blob/23ae7baddecf/test/src/unittests/rhythm/test_rhythmextractor2013.py), [key tests](https://github.com/MTG/essentia/blob/23ae7baddecf/test/src/unittests/extractor/test_keyextractor.py). | AGPL-3.0-or-later / проверить отдельную коммерческую лицензию; Windows upstream заявляет, но текущие wheels/сборку проверить. Дорогой по зависимостям/лицензии опциональный кандидат; estimates/confidence не автоматически калиброваны под наш корпус. |

**Покрытие задач анализа.** BPM/beat/onset и спектр/тембр: librosa или
Essentia. Key: Essentia, chroma в librosa — только вход в детектор. Гармония,
chord labels, размер, downbeat и структура — отдельные алгоритмы/модели;
сегментация recurrence в librosa даёт границы/сходство, не гарантирует названия
«куплет/припев» или значимость. В Essentia есть дополнительные алгоритмы,
но надёжность/лицензии моделей и их Windows-поставку здесь не квалифицировали.
Не обещаем надёжность, точность или confidence без валидации на размеченном
корпусе; результат анализа должен требовать подтверждения человеком.

## DAW и соседние движки: что переносимо

* **Mixxx** GPL-семейство, Windows поддерживается: [SoundTouch analyzer](https://github.com/mixxxdj/mixxx/blob/64c1cbec91a8/src/analyzer/plugins/analyzersoundtouchbeats.cpp), [Beats](https://github.com/mixxxdj/mixxx/blob/64c1cbec91a8/src/track/beats.cpp), [BpmControl](https://github.com/mixxxdj/mixxx/blob/64c1cbec91a8/src/engine/controls/bpmcontrol.cpp), [тест BpmControl](https://github.com/mixxxdj/mixxx/blob/64c1cbec91a8/src/test/bpmcontrol_test.cpp). Различает сетку, темп и позицию; SoundTouch analyzer получает средний BPM, не доказанную сетку. [1](https://github.com/mixxxdj/mixxx/wiki/Beat-and-Bar-Edit-Workflow) описывает grid и beat map; wiki может описывать проектируемое, не гарантировать наличие каждой функции. Полезно: явные anchor и фазу бита не смешивать с абсолютным BPM.
* **Audacity**, GPL-семейство, Windows: [TimeStretching](https://github.com/audacity/audacity/blob/1016711487c3/au3/libraries/au3-wave-track/TimeStretching.cpp) обновляет длительность клипа при смене ratio; [Mix.cpp](https://github.com/audacity/audacity/blob/1016711487c3/au3/libraries/au3-mixer/Mix.cpp), [compressor tests](https://github.com/audacity/audacity/blob/1016711487c3/au3/libraries/au3-dynamic-range-processor/tests/CompressorProcessorTests.cpp). Это примеры клипов и потокового сведения, а не готовый backend, совпадающий с нашим contract.
* **Ardour**, GPL-семейство, Windows поддерживается: [st_stretch.cc](https://github.com/Ardour/ardour/blob/9500a47c504f/libs/ardour/st_stretch.cc) использует SoundTouch и `setTempo(1.0 / stretch)`, подавая и извлекая блоки; [sp_stretch.cc](https://github.com/Ardour/ardour/blob/9500a47c504f/libs/ardour/sp_stretch.cc), [audio engine test](https://github.com/Ardour/ardour/blob/9500a47c504f/libs/ardour/test/audio_engine_test.cc). Важен перевод «множитель длительности» в API скорости. Не доказано, что их политика границ идентична нашей.
* **REAPER**, закрытый исходный код, коммерческая лицензия, Windows: публичное [1](https://dlx.reaper.fm/userguide/html/) описывает project/item timebase и stretch markers. Урок: смена project BPM может по-разному влиять на позиции и длительности; маркеры задают локальные соответствия. Исходники и тесты аудиодвижка недоступны для аудита, не приписываем ему bit-exact гарантии.
* **JUCE**, лицензия текущего дерева AGPLv3 или коммерческая: [graph](https://github.com/juce-framework/JUCE/blob/d60b7a780306/modules/juce_audio_processors_headless/processors/juce_AudioProcessorGraph.cpp), [ResamplingAudioSource](https://github.com/juce-framework/JUCE/blob/d60b7a780306/modules/juce_audio_basics/sources/juce_ResamplingAudioSource.cpp), [license](https://github.com/juce-framework/JUCE/blob/d60b7a780306/LICENSE.md). С++ framework с Windows, но graph/устройства/plugins намного шире offline MVP; не выбирать весь framework только ради SRC. Полноценные тесты JUCE здесь не запущены.
* **Wavelength** (предположительно имеется в виду [austinginder/wavelength](https://github.com/austinginder/wavelength), а не одноимённые проигрыватели): MIT, upstream описывает Windows build; [engine.cpp](https://github.com/austinginder/wavelength/blob/e6174addc55b/src/engine.cpp) явно преобразует время событий в sample positions, имеет plugin warm-up и исправление некорректных сэмплов; [release test](https://github.com/austinginder/wavelength/blob/e6174addc55b/scripts/release-test.py) проверяет рендер/упаковку. Это плагинный MIDI-инструмент, не доказательство детерминированного PCM и не совместимый исходный контракт: например, он заглушает невалидные сэмплы, а Mashup Lab должен выдавать ошибку. Автоматическую генерацию и плагины не переносим.
* **Produzre**, MIT, Python/Windows: [rng.py](https://github.com/repsac/produzre/blob/ff787029ddcc/produzre/rng.py) использует SHA-256 и разделённые scope seeds, [MIDI determinism tests](https://github.com/repsac/produzre/blob/ff787029ddcc/tests/test_midi_determinism.py) сравнивают MIDI. Это не доказательство PCM-детерминизма и не причина вводить случайность в MVP.
* **Open Generative Studios**: найденный [репозиторий](https://github.com/medyassinekhlif/open-generative-studios/tree/23ae930925f2) содержит README, два PDF и изображения; исходный код сервиса и тесты в этом дереве отсутствуют, лицензия не определена. Заявленное разделение MIDI → stems → mix можно считать только описанием; пригодность для интеграции, Windows и воспроизводимость **не проверяемы по данному дереву**. Генерацию не рассматриваем.

## Синхронизация: разные задачи, разные гарантии

1. **Tempo match**: при проверенных постоянных BPM источника и цели требуемый
   множитель длительности = source BPM / target BPM, например 120→125 = 0.96.
   API скорости SoundTouch требует обратную величину. Один ratio не устраняет
   дрейф при переменном темпе.
2. **Beat phase / offset**: известный source-frame первого бита плюс целевой
   timeline frame даёт сдвиг после учёта обработки и начала интервала. BPM без
   точки привязки не определяет фазу. Beat phase — не фаза колебаний волны.
3. **Drift/warp**: последовательность пар якорей или beat-map позволяет
   описать локальную скорость. DTW подходит для похожих записей/музыкальных
   признаков, но не гарантирует соответствие произвольных песен; потребуются
   monotonicity, ограничения скорости, ручная коррекция и оценка уверенности.
   Планы версионировать, но новую схему сейчас не вводить.
4. **Фаза waveform**: корреляция/GCC-PHAT способна оценивать задержку у
   достаточно похожих сигналов, но для разных песен/разных микрофонов может
   быть неопределённой; в частотных компонентах phase-wrap, неоднозначные пики,
   отражения и silence. Полярность — не универсальная «коррекция фазы». Нельзя
   автоматически переворачивать/выравнивать все дорожки. Изученные `scipy.signal.correlate` и его тесты — только примитив; задача
   подбора надёжного offset и критерий отказа для наших файлов не проверены.
5. **Физическое сохранение отношений**: одинаковый warp/delay по каналам и
   связанным stem-группам нужно тестировать отдельно. Независимая обработка
   связанных дорожек может изменить взаимную фазу, даже при совпадении длины;
   степень зависит от конкретного backend и входа.

## Сопоставление с Mashup Lab

| Область | Состояние | Что оставить / дефицит |
|---|---|---|
| Формат, числа, идентичность | Реализовано частично | [model.py](../mashup/model.py): YAML, SHA, WAV, рациональное время. Нет авторского происхождения или гарантии защиты от враждебных гонок. |
| План | Реализовано | `plan_project` и [независимый валидатор](../mashup/plan_validation.py); попарные пересечения по порядку клипов. `plan` только геометрия, не graph; самостоятельная проверка не связывает его с проектом. |
| Binding | Реализован узкий in-process срез | [render.py](../mashup/render.py) строит план из единого объекта и декодирует те же source bytes, что хешируются. Нет manifest, сохранённый план не принимается; это не trust admission. |
| PCM, стерео, gain/pan/fades/mix, peak, WAV | Частично реализовано | 48 kHz, mono/stereo integer PCM, ratio 1 и pitch 0; no dither. Это sample-peak scaling всего микса, не true peak, limiter или LUFS. Несколько версий окружения не закреплены. |
| SRC, независимые stretch/pitch | Не реализовано | Выбирать существующие библиотеки и адаптер; исследовать критическую границу/context ниже. |
| Линейный конвейер и effect state | Частично определён | Порядок задан текстом; типы буферов, state/flush и временные карты требуют уточнения. Универсальный graph API и plugin host не нужны для MVP. |
| Синхронизация и анализ | Не реализовано | Ручные координаты/ratio допускаются форматом; источник BPM, offset и beatmap не представлены. Для MVP достаточно ручных решений; возможный анализ — отдельно с явным подтверждением. |
| Render manifest / профиль | Не реализовано | Есть draft; отсутствуют фактические profile lock и manifest. Хеш PCM в stdout — диагностика, не manifest. |
| Streaming/память | Ограничение текущей реализации | Сырые байты, декодированные источники и весь выход живут в памяти. Глобальный пик требует второй проход либо временное хранение; параллелизм не должен менять порядок суммы. Оптимизация — после оценки размеров проектов и квалификации DSP, не блокер MVP. |
| Генерация, VST host, GUI, авто-мастеринг | Неактуально для MVP | Не добавлять по итогам этого аудита. |

## Эксперимент: soxr, границы и блоки

Выполнено локально в изолированной временной виртуальной среде Linux x86-64:
Python 3.11.2, NumPy 2.4.6, python-soxr 1.1.0, libsoxr `0.1.3-14-ga66f3ee`,
HQ, float32. Тест не проверяет Windows или качество музыкального звучания.

* Импульс в frame 5000, 44100 frames стерео при 44100 Hz → 48000 Hz: 48000
  output frames; максимум в frame 5442. Два one-shot результата идентичны;
  stream по 1000 input frames с `last=True` на последнем блоке тоже побитово
  совпал с one-shot в этом случае. Первый блок выдал 889 output frames, а не
  пропорциональную длину — необходимо корректно слить конец и обработать задержку.
* Непрерывный float32 синус 10 kHz, амплитуда 0.5, 2 s при 44100 Hz:
  one-shot SRC и два независимо пересчитанных 1-секундных куска имеют по 96000
  frames, но у склейки максимальная абсолютная разница **0.0232402086** на
  output frame 48002; вдали от стыка (frames 5000..46999) в этом запуске 0.
  Это не доказывает слышимый щелчок на каждом материале и не ошибка soxr:
  независимые входы имеют разные контекст и boundary conditions.
* Дополнительно исследованы input lengths 1, 2, 3, 10, 100: output lengths
  1, 2, 3, 11, 109, совпали с нашим half-up в этих случаях. Это **не** доказательство
  совпадения всех дробных случаев и взаимодействия с stretch.

Минимальное воспроизведение второго сравнения:

```python
import numpy as np, soxr
x = (.5 * np.sin(2*np.pi*10000*np.arange(88200)/44100)).astype(np.float32)
a = soxr.resample(x, 44100, 48000, quality='HQ')
b = np.concatenate([soxr.resample(x[:44100], 44100, 48000, quality='HQ'),
                    soxr.resample(x[44100:], 44100, 48000, quality='HQ')])
print(len(a), len(b), np.max(np.abs(a-b)), np.argmax(np.abs(a-b)))
```

## Выводы по детерминизму

Порядок **планирования независимых вычислений** можно менять, но требование
«независимость от порядка суммирования» несовместимо с обычным binary64:
`(1e16 + -1e16) + 1 = 1`, а `1e16 + (-1e16 + 1) = 0`. Нужны фиксированные
порядок клипов и дерево редукции; изменение порядка клипов в текущем формате
может менять результат. Потоки могут готовить разные клипы параллельно, но
накопление должно сохранить определённый порядок и не разделять stateful backend
между потоками без правил. Число потоков, SIMD, FFT, компилятор и backend влияют
на результат. Пины, независимые математические эталоны и повторные PCM-хеши
необходимы; наличие seed, совпадение геометрии и CI pass недостаточны.

## Открытые проверки и критерии выбора

1. Лицензия самого Mashup Lab и способ поставки каждой DLL/wheel/FFmpeg build;
   юридическая совместимость и коммерческие условия — отдельное решение.
2. Зафиксировать версии, float mode, thread count и Windows 10/11 x64 build;
   сопоставить one-shot/streaming, блоки 1/127/1024 и reset/flush.
3. Эталонные impulse, DC, sweep, Nyquist/alias, stereo-phase, короткие/тишина,
   odd lengths, fade/rounding и точность позиции транзиента; сравнить длину и
   ожидаемые bounds независимо от hash.
4. Для stretch: речь, вокал, ударные, полифония, коррелированные stems,
   ratio 0.96/1/1.04 и крайние 0.5/2, pitch ±1/±12; фиксировать артефакты и
   blind listening, реальное время/память, качество на Windows. Раздельные и
   совместные операции сравнивать как разные профили, не считать равными.
5. Для анализа: размеченный легально доступный набор с tempo changes,
   syncopation, silence и разными стилями; измерять beat/downbeat precision,
   offset/drift, key accuracy, rejection/coverage и manual-correction cost;
   оценка confidence без калибровки не гарантия.
6. Не переносить лицензированный исходный код из DAW, не подключать vendor и не
   менять production до согласования рекомендаций.
