from pathlib import Path

main = Path("AsistenciaObraPE/app/src/main/java/pe/asistencia/obra/MainActivity.java")
s = main.read_text(encoding="utf-8")

old_info = '''        info.setText("El archivo CSV abre directamente en Excel y puede compartirse por WhatsApp, Drive o correo. " +
                "Por seguridad, NO exporta números de cuenta ni datos SUNAT.");'''
new_info = '''        info.setText("El CSV se exporta como cuadro de asistencia: una fila por trabajador y una columna por fecha. " +
                "Así puedes abrirlo en Excel, copiar las columnas de A/M/F y pegarlas en tu control de asistencia. " +
                "Por seguridad, NO exporta números de cuenta ni datos SUNAT.");'''
if old_info not in s:
    raise SystemExit("No se encontró el texto de exportación original")
s = s.replace(old_info, new_info)

start_marker = "    private void exportCsv(LocalDate start, LocalDate end, String type) {"
end_marker = "\n    private void pickDate(DatePicked callback) {"
start = s.index(start_marker)
end = s.index(end_marker, start)

new_method = r'''    private void exportCsv(LocalDate start, LocalDate end, String type) {
        List<Worker> workers = db.searchWorkers("", false);
        workers.sort((a, b) -> Long.compare(a.id, b.id));

        List<Worker> eligibleWorkers = new ArrayList<>();
        for (Worker w : workers) {
            try {
                LocalDate created = LocalDate.parse(w.createdAt.substring(0, 10));
                if (!created.isAfter(end)) eligibleWorkers.add(w);
            } catch (Exception ignored) {
                eligibleWorkers.add(w);
            }
        }

        List<LocalDate> dates = new ArrayList<>();
        for (LocalDate d = start; !d.isAfter(end); d = d.plusDays(1)) {
            // El Excel de obra trabaja de lunes a sábado; domingo no se exporta.
            if (d.getDayOfWeek().getValue() != 7) dates.add(d);
        }

        DateTimeFormatter columnDate = DateTimeFormatter.ofPattern("EEE dd/MM", new Locale("es", "PE"));
        int[] fullByDate = new int[dates.size()];
        int[] halfByDate = new int[dates.size()];
        int[] absentByDate = new int[dates.size()];

        StringBuilder csv = new StringBuilder();
        csv.append('\uFEFF');
        csv.append(CoreUtils.csv("N.º")).append(';')
                .append(CoreUtils.csv("Nombres y apellidos")).append(';')
                .append(CoreUtils.csv("Categoría")).append(';')
                .append(CoreUtils.csv("WhatsApp"));

        for (LocalDate d : dates) {
            String header = columnDate.format(d);
            if (!header.isEmpty()) {
                header = header.substring(0, 1).toUpperCase(new Locale("es", "PE")) + header.substring(1);
            }
            csv.append(';').append(CoreUtils.csv(header));
        }
        csv.append('\n');

        int rowNumber = 1;
        for (Worker w : eligibleWorkers) {
            csv.append(CoreUtils.csv(String.valueOf(rowNumber++))).append(';')
                    .append(CoreUtils.csv(w.name)).append(';')
                    .append(CoreUtils.csv(w.trade)).append(';')
                    .append(CoreUtils.csv(w.whatsapp));

            LocalDate created = null;
            try {
                created = LocalDate.parse(w.createdAt.substring(0, 10));
            } catch (Exception ignored) {}

            for (int i = 0; i < dates.size(); i++) {
                LocalDate d = dates.get(i);
                String status = "";
                if (created == null || !d.isBefore(created)) {
                    status = db.getAttendance(w.id, d.toString());
                }

                if ("A".equals(status)) fullByDate[i]++;
                else if ("M".equals(status)) halfByDate[i]++;
                else if ("F".equals(status)) absentByDate[i]++;

                csv.append(';').append(CoreUtils.csv(status));
            }
            csv.append('\n');
        }

        // Resumen separado para no interferir al copiar el cuadro de trabajadores.
        csv.append('\n');
        csv.append(CoreUtils.csv("RESUMEN - NO PEGAR EN LA TABLA DE PERSONAL")).append(';')
                .append(CoreUtils.csv("")).append(';')
                .append(CoreUtils.csv("")).append(';')
                .append(CoreUtils.csv(""));
        for (int i = 0; i < dates.size(); i++) csv.append(';').append(CoreUtils.csv(""));
        csv.append('\n');

        appendSummaryRow(csv, "Total A", fullByDate);
        appendSummaryRow(csv, "Total M", halfByDate);
        appendSummaryRow(csv, "Total F", absentByDate);

        csv.append(CoreUtils.csv("Jornales eq.")).append(';')
                .append(CoreUtils.csv("")).append(';')
                .append(CoreUtils.csv("")).append(';')
                .append(CoreUtils.csv(""));
        for (int i = 0; i < dates.size(); i++) {
            double jornales = fullByDate[i] + halfByDate[i] * 0.5;
            String value = (jornales == Math.rint(jornales))
                    ? String.valueOf((int) jornales)
                    : String.format(Locale.US, "%.1f", jornales);
            csv.append(';').append(CoreUtils.csv(value));
        }
        csv.append('\n');

        String suffix;
        if (start.equals(end)) suffix = start.toString();
        else suffix = start.toString() + "_a_" + end.toString();
        String filename = "Asistencia_Cuadro_" + type + "_" + suffix + ".csv";

        ContentValues values = new ContentValues();
        values.put(MediaStore.MediaColumns.DISPLAY_NAME, filename);
        values.put(MediaStore.MediaColumns.MIME_TYPE, "text/csv");
        values.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/AsistenciaObra");
        values.put(MediaStore.MediaColumns.IS_PENDING, 1);

        Uri collection = MediaStore.Downloads.EXTERNAL_CONTENT_URI;
        Uri uri = getContentResolver().insert(collection, values);
        if (uri == null) {
            Toast.makeText(this, "No se pudo crear el archivo.", Toast.LENGTH_LONG).show();
            return;
        }

        try (OutputStream out = getContentResolver().openOutputStream(uri)) {
            if (out == null) throw new IllegalStateException("Sin salida de archivo.");
            out.write(csv.toString().getBytes(StandardCharsets.UTF_8));
            out.flush();

            values.clear();
            values.put(MediaStore.MediaColumns.IS_PENDING, 0);
            getContentResolver().update(uri, values, null, null);

            Toast.makeText(this,
                    "Cuadro exportado. Abre el CSV en Excel y copia las columnas de fechas.",
                    Toast.LENGTH_LONG).show();

            Intent share = new Intent(Intent.ACTION_SEND);
            share.setType("text/csv");
            share.putExtra(Intent.EXTRA_STREAM, uri);
            share.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            startActivity(Intent.createChooser(share, "Compartir cuadro de asistencia"));
        } catch (Exception e) {
            getContentResolver().delete(uri, null, null);
            Toast.makeText(this, "Error al exportar: " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    private void appendSummaryRow(StringBuilder csv, String label, int[] values) {
        csv.append(CoreUtils.csv(label)).append(';')
                .append(CoreUtils.csv("")).append(';')
                .append(CoreUtils.csv("")).append(';')
                .append(CoreUtils.csv(""));
        for (int value : values) csv.append(';').append(CoreUtils.csv(String.valueOf(value)));
        csv.append('\n');
    }
'''

s = s[:start] + new_method + s[end:]
main.write_text(s, encoding="utf-8")

gradle = Path("AsistenciaObraPE/app/build.gradle")
g = gradle.read_text(encoding="utf-8")
g = g.replace("versionCode 1", "versionCode 2")
g = g.replace("versionName '1.0.0'", "versionName '1.1.0'")
gradle.write_text(g, encoding="utf-8")
