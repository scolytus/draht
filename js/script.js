// Inspired by:
// http://runnable.com/UhY_jE3QH-IlAAAP/how-to-parse-a-json-file-using-jquery

//When DOM loaded we attach click event to button
$(document).ready(function() {

    $.ajaxSetup({ cache: false });

    //after button is clicked we download the data
    $('.button').click(function(){

        //start ajax request
        $.ajax({
            url: "latest.json",
            //force to handle it as text
            dataType: "text",
            success: function(data) {

                //data downloaded so we call parseJSON function
                //and pass downloaded data
                var json = $.parseJSON(data);

                var index;
                var content = '<tr><th>Player</th><th>Time</th><th>Contacts</th></tr>\n';
                for (index = 0; index < json.results.length; ++index) {
                    content += "<tr><td>" +  json.results[index]['id'] +
                               "</td><td>" + json.results[index]['time'] +
                               "</td><td>" + json.results[index]['contacts'] +
                               "</td></tr>\n";
                }

                $('#round_number').html(json.round);
                $('#round_start').html(json.start);
                $('#results_table').html(content);
            }
        });
    });
});

